"""Insider (Form 4) activity from SEC EDGAR, scoped to each issuer's own
submissions feed — never full-text search, which would match unrelated
filings for short/common tickers like 'S' or 'U'.

Two consumers:
- the weekly run wants net open-market dollars in a trailing window;
- the backtest wants the full dated history so it can window any as-of date.
Both share `fetch_form4_history`, which parses each Form 4 XML exactly once.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import date, timedelta

from .edgar import EdgarClient

log = logging.getLogger(__name__)

LOOKBACK_DAYS = 14
MAX_FILINGS_PER_TICKER = 10   # weekly-run bound
MAX_HISTORY_FILINGS = 80      # backtest bound (years of Form 4s for a small cap)


def parse_form4(xml_text: str) -> tuple[float, float]:
    """Net (buy_dollars, sell_dollars) from a Form 4's open-market
    transactions — code P (purchase) and S (sale) only, ignoring awards,
    option exercises, tax withholding, and gifts."""
    buy = sell = 0.0
    root = ET.fromstring(xml_text)
    for tx in root.iter("nonDerivativeTransaction"):
        code = tx.findtext("transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue
        shares = tx.findtext("transactionAmounts/transactionShares/value")
        price = tx.findtext("transactionAmounts/transactionPricePerShare/value")
        try:
            dollars = float(shares) * float(price)
        except (TypeError, ValueError):
            continue
        if code == "P":
            buy += dollars
        else:
            sell += dollars
    return buy, sell


def fetch_form4_history(
    client: EdgarClient,
    ticker: str,
    since: date,
    max_filings: int = MAX_FILINGS_PER_TICKER,
) -> list[tuple[date, float]] | None:
    """[(filing_date, net_dollars)] for the issuer's Form 4s since `since`,
    newest first. None when the ticker can't be resolved or EDGAR fails.
    A filing whose XML can't be fetched/parsed contributes zero dollars."""
    cik = client.cik_for(ticker)
    if cik is None:
        log.info("no CIK found for %s; insider signal unavailable", ticker)
        return None
    try:
        filings = client.recent_filings(cik)
    except Exception as exc:  # noqa: BLE001 — per-ticker failures are non-fatal
        log.warning("EDGAR submissions fetch failed for %s: %s", ticker, exc)
        return None

    cutoff = since.isoformat()
    form4s = [
        f
        for f in filings
        if f["form"] == "4" and f["filingDate"] >= cutoff
    ][:max_filings]

    out: list[tuple[date, float]] = []
    for f in form4s:
        net = 0.0
        if f["primaryDocument"].endswith(".xml"):
            try:
                xml_text = client.filing_text(
                    cik, f["accessionNumber"], f["primaryDocument"]
                )
                buy, sell = parse_form4(xml_text)
                net = buy - sell
            except Exception as exc:  # noqa: BLE001 — skip unparseable filings
                log.debug(
                    "Form 4 parse failed for %s %s: %s",
                    ticker,
                    f["accessionNumber"],
                    exc,
                )
        out.append((date.fromisoformat(f["filingDate"]), net))
    return out


def window_activity(
    history: list[tuple[date, float]] | None, as_of: date, lookback_days: int
) -> dict | None:
    """Aggregate a Form 4 history into {net_dollars, filings} for the window
    (as_of - lookback, as_of]. None history stays None (no information)."""
    if history is None:
        return None
    start = as_of - timedelta(days=lookback_days)
    in_window = [(d, net) for d, net in history if start < d <= as_of]
    return {
        "net_dollars": sum(net for _, net in in_window),
        "filings": len(in_window),
    }


def fetch_form4_activity(
    tickers: list[str],
    user_agent: str | None = None,
    lookback_days: int = LOOKBACK_DAYS,
    client: EdgarClient | None = None,
) -> dict[str, dict | None]:
    """Weekly-run entrypoint: trailing-window activity per shortlist ticker."""
    client = client or EdgarClient(user_agent or "")
    today = date.today()
    since = today - timedelta(days=lookback_days)
    log.info("Fetching Form 4 activity for %d shortlisted tickers", len(tickers))
    return {
        t: window_activity(
            fetch_form4_history(client, t, since), today, lookback_days
        )
        for t in tickers
    }
