"""Market data via yfinance: batched OHLCV history and per-ticker fundamentals.

yfinance scrapes Yahoo Finance — there is no official contract, so every call
is wrapped defensively: a ticker that errors is skipped and logged, never fatal.
"""

from __future__ import annotations

import logging
import statistics
import time

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

# Fields pulled from Ticker.info for the fundamentals signal.
FUNDAMENTAL_FIELDS = [
    "marketCap",
    "trailingPE",
    "forwardPE",
    "revenueGrowth",
    "debtToEquity",
    "dividendYield",   # fetched for reporting only — not scored, see signals/fundamentals.py
    "returnOnEquity",
    "grossMargins",
    "operatingCashflow",
    "netIncomeToCommon",
    # valuation multiples (for the valuation signal)
    "priceToSalesTrailing12Months",
    "enterpriseToRevenue",
    "enterpriseToEbitda",
    "pegRatio",
    "freeCashflow",
    # short interest (for the short_interest signal) — rides along free
    "sharesShort",
    "sharesShortPriorMonth",
    "shortPercentOfFloat",
    "sector",
    "shortName",
]

INFO_BATCH_PAUSE_EVERY = 25  # gentle pacing for the per-ticker info endpoint
INFO_BATCH_PAUSE_SECS = 1.0

# Share-count history settings. Values chosen from the live measurement in
# scripts/diagnose_share_change.py (40 tickers, 4 years): the series is dense
# (median gap 1 day, 429 observations/ticker) but gaps reach 165 days, and the
# index comes back tz-aware for most tickers and naive for a few.
SHARE_LOOKBACK_DAYS = 365
SHARE_ENDPOINT_OBS = 5             # median over this many points at each end
SHARE_WINDOW_TOLERANCE_DAYS = 120  # how far the first point may sit from target
SPLIT_TOLERANCE = 0.05             # closeness to n or 1/n to call a jump a split


def fetch_price_history(tickers: list[str], period: str = "1y") -> pd.DataFrame:
    """Batched daily OHLCV for all tickers in one yf.download call.

    Returns the yfinance multi-column frame (columns level 0 = field,
    level 1 = ticker). Tickers with no data simply have NaN columns.
    """
    log.info("Fetching %s of price history for %d tickers", period, len(tickers))
    data = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        group_by="column",
        auto_adjust=True,
        threads=True,
        progress=False,
    )
    # Single-ticker downloads come back without the ticker column level;
    # normalize so callers always see (field, ticker).
    if len(tickers) == 1 and not isinstance(data.columns, pd.MultiIndex):
        data.columns = pd.MultiIndex.from_product([data.columns, tickers])
    return data


def fetch_fundamentals(tickers: list[str]) -> pd.DataFrame:
    """Per-ticker Ticker.info pulls, fault-isolated. Returns a DataFrame
    indexed by ticker with FUNDAMENTAL_FIELDS columns; failed tickers are
    dropped (and counted in the 'skipped' log line)."""
    rows: dict[str, dict] = {}
    skipped: list[str] = []
    for i, ticker in enumerate(tickers):
        try:
            info = yf.Ticker(ticker).info
            if not info or info.get("marketCap") is None:
                skipped.append(ticker)
                continue
            rows[ticker] = {f: info.get(f) for f in FUNDAMENTAL_FIELDS}
        except Exception as exc:  # noqa: BLE001 — any per-ticker failure is non-fatal
            log.warning("fundamentals fetch failed for %s: %s", ticker, exc)
            skipped.append(ticker)
        if (i + 1) % INFO_BATCH_PAUSE_EVERY == 0:
            time.sleep(INFO_BATCH_PAUSE_SECS)
    if skipped:
        log.info("fundamentals: skipped %d/%d tickers", len(skipped), len(tickers))
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "ticker"
    return df


def normalize_share_index(shares: pd.Series) -> pd.Series:
    """Flatten get_shares_full's index to naive, sorted, deduplicated dates.

    Measured on 40 live tickers, the endpoint returns a MIX: 38 came back
    tz-aware (America/New_York) and 2 tz-naive. Comparing the two raises in
    pandas, so any date arithmetic over a mixed set is a latent crash — and
    the backtest slices these by as-of date for every rebalance.
    """
    idx = pd.to_datetime(shares.index, errors="coerce", utc=True)
    out = pd.Series(shares.to_numpy(), index=idx.tz_localize(None), dtype="float64")
    out = out[out.index.notna()].dropna()
    return out[~out.index.duplicated(keep="last")].sort_index()


def _split_ratio(ratio: float) -> float | None:
    """The clean split factor a jump represents, or None if it isn't one."""
    if ratio <= 0:
        return None
    for n in range(2, 21):
        if abs(ratio - n) / n <= SPLIT_TOLERANCE:
            return float(n)
        if abs(ratio - 1.0 / n) * n <= SPLIT_TOLERANCE:
            return 1.0 / n
    return None


def split_adjust(values: list[float]) -> list[float]:
    """Restate a raw share count onto the most recent split basis.

    A split changes the share count without changing anything economic: 2:1
    doubles it, which the raw ratio reads as +100% dilution — the worst
    possible rank on this signal — while a reverse split reads as a large
    buyback and ranks best. It fails in the most damaging direction available.

    Honest scope: measured across 40 tickers over 4 years this fired ZERO
    times. Small/mid-cap tech rarely splits; that is mega-cap behaviour. So
    this is a guard against a latent trap, not a fix for an active defect —
    but the failure it prevents is severe, silent, and would look like a
    legitimate score.
    """
    n = len(values)
    if n < 2:
        return list(values)
    factors = [1.0] * n
    cumulative = 1.0
    for i in range(n - 1, 0, -1):
        if values[i - 1] > 0:
            factor = _split_ratio(values[i] / values[i - 1])
            if factor:
                cumulative *= factor
        factors[i - 1] = cumulative
    return [v * f for v, f in zip(values, factors)]


def fetch_share_change(
    tickers: list[str], lookback_days: int = SHARE_LOOKBACK_DAYS
) -> pd.Series:
    """Trailing change in shares outstanding per ticker (+0.08 = 8% dilution).

    NaN — not omission — where history is unusable, so the caller can tell
    "no data" from "not requested". The previous version dropped such tickers
    silently with no log line at all, which meant share coverage could collapse
    to zero while score_quality stayed fully populated on accruals alone. That
    is the invisible-coverage failure that manufactured the insider IC reverted
    in #24.

    Three robustness measures, each grounded in the live measurement:
    - the series is split-adjusted before differencing (see split_adjust);
    - endpoints are the MEDIAN of SHARE_ENDPOINT_OBS observations rather than
      single points, so one bad print cannot set the score. The series is dense
      enough for this — median gap between observations is 1 day;
    - the first observation must land within SHARE_WINDOW_TOLERANCE_DAYS of the
      target start, else NaN. Gaps reach 165 days, so `iloc[0]` is not reliably
      "a year ago", and a short window is not a smaller sample — it is a
      different measurement that is not comparable across tickers.
    """
    import datetime as _dt

    target_start = _dt.date.today() - _dt.timedelta(days=lookback_days)
    fetch_start = target_start - _dt.timedelta(days=SHARE_WINDOW_TOLERANCE_DAYS)
    out: dict[str, float] = {}
    short_history = stale_start = failed = 0

    for i, ticker in enumerate(tickers):
        try:
            raw = yf.Ticker(ticker).get_shares_full(start=fetch_start.isoformat())
            if raw is None or len(raw) < 2:
                short_history += 1
                continue
            shares = normalize_share_index(raw)
            if len(shares) < 2:
                short_history += 1
                continue
            # The window must actually be ~lookback_days long to compare across
            # tickers; a first point far from target is a different measurement.
            first = shares.index[0].date()
            if abs((first - target_start).days) > SHARE_WINDOW_TOLERANCE_DAYS:
                stale_start += 1
                continue
            adjusted = split_adjust([float(v) for v in shares.to_numpy()])
            k = min(SHARE_ENDPOINT_OBS, len(adjusted) // 2) or 1
            begin = statistics.median(adjusted[:k])
            end = statistics.median(adjusted[-k:])
            if begin <= 0:
                short_history += 1
                continue
            out[ticker] = float(end / begin - 1.0)
        except Exception as exc:  # noqa: BLE001 — per-ticker failure is non-fatal
            failed += 1
            log.debug("share history failed for %s: %s", ticker, exc)
        if (i + 1) % INFO_BATCH_PAUSE_EVERY == 0:
            time.sleep(INFO_BATCH_PAUSE_SECS)

    # Aggregate, at info level, mirroring fetch_fundamentals. A silent collapse
    # of this source must never again be invisible.
    log.info(
        "share change: %d/%d tickers usable (%d short history, %d start too far "
        "from target, %d fetch errors)",
        len(out), len(tickers), short_history, stale_start, failed,
    )
    return pd.Series(out, dtype="float64").reindex(tickers)


def fetch_profitability_metrics(tickers: list[str]) -> pd.DataFrame:
    """Balance-sheet factors per ticker: gross profitability and asset growth.

    - gp_over_assets: gross profit / total assets (Novy-Marx 2013, "the other
      side of value") — the profitability measure that survived replication
      best, and cleaner than ROE because gross profit sits above the accrual
      and financing choices that pollute net income.
    - asset_growth: YoY total-asset growth (Cooper/Gulen/Schill 2008) — high
      growers underperform; it's the CMA leg of Fama-French five-factor.

    Two extra statement pulls per ticker, so shortlist-only (Stage B). NaN
    rows where statements are unavailable — the signal treats that as 'no
    information', never zero.
    """
    rows: dict[str, dict] = {}
    for i, ticker in enumerate(tickers):
        gp = assets = assets_prev = None
        try:
            tk = yf.Ticker(ticker)
            bs = tk.balance_sheet
            if bs is not None and not bs.empty and "Total Assets" in bs.index:
                series = bs.loc["Total Assets"].dropna()
                if len(series) >= 1:
                    assets = float(series.iloc[0])
                if len(series) >= 2:
                    assets_prev = float(series.iloc[1])
            inc = tk.income_stmt
            if inc is not None and not inc.empty and "Gross Profit" in inc.index:
                gp_series = inc.loc["Gross Profit"].dropna()
                if len(gp_series) >= 1:
                    gp = float(gp_series.iloc[0])
        except Exception as exc:  # noqa: BLE001 — per-ticker failure is non-fatal
            log.debug("statement fetch failed for %s: %s", ticker, exc)
        rows[ticker] = {
            "gp_over_assets": (gp / assets) if gp is not None and assets else None,
            "asset_growth": (
                assets / assets_prev - 1.0
                if assets is not None and assets_prev
                else None
            ),
        }
        if (i + 1) % INFO_BATCH_PAUSE_EVERY == 0:
            time.sleep(INFO_BATCH_PAUSE_SECS)
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "ticker"
    return df
