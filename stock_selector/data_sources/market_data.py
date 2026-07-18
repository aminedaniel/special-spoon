"""Market data via yfinance: batched OHLCV history and per-ticker fundamentals.

yfinance scrapes Yahoo Finance — there is no official contract, so every call
is wrapped defensively: a ticker that errors is skipped and logged, never fatal.
"""

from __future__ import annotations

import logging
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
    "dividendYield",
    "returnOnEquity",
    "grossMargins",
    "operatingCashflow",
    "netIncomeToCommon",
    "sector",
    "shortName",
]

INFO_BATCH_PAUSE_EVERY = 25  # gentle pacing for the per-ticker info endpoint
INFO_BATCH_PAUSE_SECS = 1.0


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


def fetch_share_change(tickers: list[str], lookback_days: int = 365) -> pd.Series:
    """Trailing change in shares outstanding per ticker (e.g. +0.08 = 8%
    dilution over the lookback). NaN where history is unavailable."""
    import datetime as _dt

    start = _dt.date.today() - _dt.timedelta(days=lookback_days + 30)
    out: dict[str, float] = {}
    for i, ticker in enumerate(tickers):
        try:
            shares = yf.Ticker(ticker).get_shares_full(start=start.isoformat())
            if shares is None or len(shares.dropna()) < 2:
                continue
            shares = shares.dropna()
            out[ticker] = float(shares.iloc[-1] / shares.iloc[0] - 1)
        except Exception as exc:  # noqa: BLE001 — per-ticker failure is non-fatal
            log.debug("share history failed for %s: %s", ticker, exc)
        if (i + 1) % INFO_BATCH_PAUSE_EVERY == 0:
            time.sleep(INFO_BATCH_PAUSE_SECS)
    return pd.Series(out, dtype="float64")
