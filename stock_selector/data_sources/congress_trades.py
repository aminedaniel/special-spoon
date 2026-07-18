"""Congressional trading data from the free Senate/House Stock Watcher datasets.

These are public S3-hosted JSON aggregates of STOCK Act disclosures. Note the
inherent lag: members have 30-45 days to disclose, so 'recent' congressional
buys reflect trades made weeks earlier. That caveat is surfaced in the report.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import requests

log = logging.getLogger(__name__)

SENATE_URL = (
    "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/"
    "aggregate/all_transactions.json"
)
HOUSE_URL = (
    "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/"
    "data/all_transactions.json"
)
LOOKBACK_DAYS = 60  # wide window to compensate for the disclosure lag


def _parse_date(raw: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _fetch(url: str) -> list[dict]:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return resp.json()


def fetch_recent_activity(
    tickers: list[str], lookback_days: int = LOOKBACK_DAYS
) -> dict[str, dict[str, int]]:
    """Per-ticker counts of congressional purchase/sale disclosures in window.

    Returns {ticker: {"buys": n, "sells": m}} for tickers in the shortlist.
    Fails soft: if a dataset is unreachable, it contributes nothing.
    """
    wanted = set(tickers)
    cutoff = date.today() - timedelta(days=lookback_days)
    counts: dict[str, dict[str, int]] = {t: {"buys": 0, "sells": 0} for t in tickers}

    for name, url in (("senate", SENATE_URL), ("house", HOUSE_URL)):
        try:
            transactions = _fetch(url)
        except Exception as exc:  # noqa: BLE001 — one chamber failing is non-fatal
            log.warning("congress data fetch failed for %s: %s", name, exc)
            continue
        for tx in transactions:
            ticker = (tx.get("ticker") or "").strip().upper()
            if ticker not in wanted:
                continue
            tx_date = _parse_date(tx.get("transaction_date", ""))
            if tx_date is None or tx_date < cutoff:
                continue
            tx_type = (tx.get("type") or "").lower()
            if "purchase" in tx_type:
                counts[ticker]["buys"] += 1
            elif "sale" in tx_type:
                counts[ticker]["sells"] += 1
    return counts
