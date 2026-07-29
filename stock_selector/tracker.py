"""Recommendation tracker: a running ledger of the top-2 picks and how their
price has moved since the screener first recommended them.

Each new top-2 pick is anchored ONCE — to the date and price at which it first
entered the top 2 — and never re-dated, even if it drops out and returns later.
So the ledger always answers "how much has this moved since we first flagged it."

The ledger CSV (reports/recommendations.csv) is the durable source of truth:
columns [ticker, first_recommended, first_price]. The markdown is regenerated
each run with fresh current prices.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

LEDGER_COLUMNS = ["ticker", "first_recommended", "first_price"]
DEFAULT_TOP_N = 1
RANKINGS_DATE_RE = re.compile(r"rankings_(\d{4}-\d{2}-\d{2})\.csv$")


def load_ledger(path: Path) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path)
        # tolerate an empty/partial file
        for c in LEDGER_COLUMNS:
            if c not in df.columns:
                df[c] = pd.Series(dtype="object")
        return df[LEDGER_COLUMNS]
    return pd.DataFrame(columns=LEDGER_COLUMNS)


def top_picks(rankings_csv: Path, top_n: int = DEFAULT_TOP_N) -> list[str]:
    df = pd.read_csv(rankings_csv)
    if "rank" in df.columns:
        df = df.sort_values("rank")
    return df["ticker"].head(top_n).astype(str).tolist()


def add_new_picks(
    ledger: pd.DataFrame,
    picks: list[str],
    as_of: date,
    prices: dict[str, float | None],
) -> pd.DataFrame:
    """Append picks not already tracked, anchored to as_of/current price.

    A pick with no available price is skipped (not added with a bogus anchor);
    it gets another chance next run. Existing anchors are never modified.
    """
    tracked = set(ledger["ticker"].astype(str))
    rows = []
    for ticker in picks:
        if ticker in tracked:
            continue
        price = prices.get(ticker)
        if price is None or pd.isna(price):
            log.warning("no price for new pick %s; deferring", ticker)
            continue
        rows.append(
            {
                "ticker": ticker,
                "first_recommended": as_of.isoformat(),
                "first_price": float(price),
            }
        )
    if not rows:
        return ledger
    return pd.concat([ledger, pd.DataFrame(rows)], ignore_index=True)


def render_markdown(
    ledger: pd.DataFrame, current_prices: dict[str, float | None], as_of: date
) -> str:
    lines = [
        f"# Recommendation tracker — as of {as_of.isoformat()}",
        "",
        "The top pick each week, tracked from the date the screener first "
        "recommended it to the latest close. Anchors never reset.",
        "",
    ]
    if ledger.empty:
        lines.append("_No recommendations tracked yet._")
        return "\n".join(lines) + "\n"

    view = ledger.copy()
    view["first_recommended"] = pd.to_datetime(view["first_recommended"])
    view = view.sort_values("first_recommended")  # chronological ledger

    lines.append("| Ticker | First recommended | Price then | Price now | Change | Days |")
    lines.append("|---|---|---|---|---|---|")
    changes = []
    for _, row in view.iterrows():
        ticker = row["ticker"]
        then = float(row["first_price"])
        now = current_prices.get(ticker)
        rec_date = row["first_recommended"].date()
        days = (as_of - rec_date).days
        if now is None or pd.isna(now) or then <= 0:
            now_str, change_str = "—", "—"
        else:
            now = float(now)
            change = now / then - 1.0
            changes.append(change)
            now_str = f"${now:,.2f}"
            change_str = f"{change * 100:+.1f}%"
        lines.append(
            f"| {ticker} | {rec_date.isoformat()} | ${then:,.2f} | {now_str} "
            f"| {change_str} | {days} |"
        )

    if changes:
        avg = sum(changes) / len(changes)
        best = max(changes)
        worst = min(changes)
        lines += [
            "",
            f"**Tracked: {len(view)} names. Average change since recommendation: "
            f"{avg * 100:+.1f}%** (best {best * 100:+.1f}%, worst {worst * 100:+.1f}%).",
        ]
    lines += [
        "",
        "*Price-only change from the first-recommendation close; not "
        "dividend-adjusted. Automated research tracking, not investment advice.*",
        "",
    ]
    return "\n".join(lines)


def backfill_from_reports(
    ledger: pd.DataFrame,
    reports_dir: Path,
    close_on,
    top_n: int = DEFAULT_TOP_N,
) -> pd.DataFrame:
    """Seed the ledger from every past rankings_<date>.csv, anchoring each
    date's top-N to the historical close ON that report date.

    `close_on(ticker, date) -> float | None` supplies the historical price
    (injected so this is testable without network). Idempotent: a ticker
    already in the ledger keeps its original anchor and is never re-dated.
    Reports are processed oldest-first so the earliest recommendation wins.
    """
    dated_files = []
    for path in reports_dir.glob("rankings_*.csv"):
        m = RANKINGS_DATE_RE.search(path.name)
        if m:
            dated_files.append((date.fromisoformat(m.group(1)), path))
    dated_files.sort()  # oldest first

    for rec_date, path in dated_files:
        picks = top_picks(path, top_n)
        tracked = set(ledger["ticker"].astype(str))
        rows = []
        for ticker in picks:
            if ticker in tracked:
                continue
            price = close_on(ticker, rec_date)
            if price is None or pd.isna(price):
                log.warning("no historical close for %s on %s; skipping", ticker, rec_date)
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "first_recommended": rec_date.isoformat(),
                    "first_price": float(price),
                }
            )
        if rows:
            ledger = pd.concat([ledger, pd.DataFrame(rows)], ignore_index=True)
    return ledger


def historical_close(ticker: str, on: date) -> float | None:
    """Close on/just before `on` for one ticker via yfinance, fault-isolated."""
    import yfinance as yf

    try:
        data = yf.download(
            tickers=ticker,
            start=(on - timedelta(days=7)).isoformat(),
            end=(on + timedelta(days=1)).isoformat(),
            interval="1d", auto_adjust=True, progress=False,
        )
        closes = data["Close"]
        if isinstance(closes, pd.DataFrame):
            closes = closes.iloc[:, 0]
        closes = closes.dropna()
        return float(closes.iloc[-1]) if not closes.empty else None
    except Exception as exc:  # noqa: BLE001 — fail soft
        log.warning("historical close failed for %s on %s: %s", ticker, on, exc)
        return None


def fetch_current_prices(tickers: list[str]) -> dict[str, float | None]:
    """Latest close per ticker via yfinance, fault-isolated."""
    import yfinance as yf

    out: dict[str, float | None] = {t: None for t in tickers}
    if not tickers:
        return out
    try:
        data = yf.download(
            tickers=tickers, period="5d", interval="1d",
            group_by="column", auto_adjust=True, threads=True, progress=False,
        )
        closes = data["Close"]
        if isinstance(closes, pd.Series):  # single ticker
            closes = closes.to_frame(tickers[0])
        for t in tickers:
            if t in closes.columns:
                s = closes[t].dropna()
                if not s.empty:
                    out[t] = float(s.iloc[-1])
    except Exception as exc:  # noqa: BLE001 — fail soft, keep the ledger stable
        log.warning("current-price fetch failed: %s", exc)
    return out


def update_tracker(
    rankings_csv: Path | None,
    reports_dir: Path,
    top_n: int = DEFAULT_TOP_N,
    as_of: date | None = None,
    backfill: bool = False,
) -> Path:
    """Add this run's top-N picks to the ledger, refresh current prices, and
    write recommendations.md + recommendations.csv. Returns the markdown path.

    When `backfill` is set, first seed the ledger from every past
    rankings_<date>.csv using historical closes, so the ledger starts with the
    full recommendation history rather than empty.
    """
    as_of = as_of or date.today()
    ledger_path = reports_dir / "recommendations.csv"
    ledger = load_ledger(ledger_path)

    if backfill:
        ledger = backfill_from_reports(ledger, reports_dir, historical_close, top_n)

    picks = top_picks(rankings_csv, top_n) if rankings_csv is not None else []
    # Prices for everything we need to price this run: existing ledger + new picks.
    to_price = sorted(set(ledger["ticker"].astype(str)) | set(picks))
    prices = fetch_current_prices(to_price)

    ledger = add_new_picks(ledger, picks, as_of, prices)

    reports_dir.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(ledger_path, index=False)
    md_path = reports_dir / "recommendations.md"
    md_path.write_text(render_markdown(ledger, prices, as_of))
    return md_path
