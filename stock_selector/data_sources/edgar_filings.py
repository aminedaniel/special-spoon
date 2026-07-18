"""Corporate-event flags and filing-language similarity from EDGAR.

Events (point-in-time from the submissions feed, no document fetches):
  +2  SC 13D / 13D/A        activist stake with intent to influence
  +1  SC 13G / 13G/A        passive >5% stake crossing
  -1  S-3 / S-3/A           shelf registration (dilution risk)
  -2  8-K with item 4.02    previously issued financials can't be relied on

Filing text ("lazy prices"): similarity between the issuer's two most recent
same-form periodic reports (10-Q vs prior 10-Q, else 10-K vs prior 10-K).
Companies that quietly rewrite their filings tend to underperform, so HIGHER
similarity scores better. Documents are fetched once and cached per run.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
from datetime import date, timedelta

from .edgar import EdgarClient

log = logging.getLogger(__name__)

STAKE_WINDOW_DAYS = 120
SHELF_WINDOW_DAYS = 120
REDFLAG_WINDOW_DAYS = 60

EVENT_POINTS = {
    "SC 13D": 2.0,
    "SC 13D/A": 2.0,
    "SC 13G": 1.0,
    "SC 13G/A": 1.0,
    "S-3": -1.0,
    "S-3/A": -1.0,
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
SHINGLE_WORDS = 5


def event_points(
    filings: list[dict], as_of: date
) -> float:
    """Sum event points for filings inside each event type's window."""
    stake_cutoff = (as_of - timedelta(days=STAKE_WINDOW_DAYS)).isoformat()
    shelf_cutoff = (as_of - timedelta(days=SHELF_WINDOW_DAYS)).isoformat()
    redflag_cutoff = (as_of - timedelta(days=REDFLAG_WINDOW_DAYS)).isoformat()
    as_of_iso = as_of.isoformat()

    points = 0.0
    for f in filings:
        filed = f["filingDate"]
        if not filed or filed > as_of_iso:
            continue
        form = f["form"]
        if form in ("SC 13D", "SC 13D/A") and filed >= stake_cutoff:
            points += EVENT_POINTS[form]
        elif form in ("SC 13G", "SC 13G/A") and filed >= stake_cutoff:
            points += EVENT_POINTS[form]
        elif form in ("S-3", "S-3/A") and filed >= shelf_cutoff:
            points += EVENT_POINTS[form]
        elif form == "8-K" and filed >= redflag_cutoff and "4.02" in (f["items"] or ""):
            points -= 2.0
    return points


def fetch_event_points(
    tickers: list[str], client: EdgarClient, as_of: date | None = None
) -> dict[str, float | None]:
    as_of = as_of or date.today()
    out: dict[str, float | None] = {}
    for t in tickers:
        cik = client.cik_for(t)
        if cik is None:
            out[t] = None
            continue
        try:
            out[t] = event_points(client.recent_filings(cik), as_of)
        except Exception as exc:  # noqa: BLE001 — per-ticker failures are non-fatal
            log.warning("event fetch failed for %s: %s", t, exc)
            out[t] = None
    return out


def strip_html(text: str) -> str:
    return _WS_RE.sub(" ", html_lib.unescape(_TAG_RE.sub(" ", text))).lower()


def shingle_similarity(a: str, b: str, k: int = SHINGLE_WORDS) -> float:
    """Jaccard similarity over word k-shingles (order-sensitive, fast)."""
    wa, wb = a.split(), b.split()
    sa = {tuple(wa[i : i + k]) for i in range(max(len(wa) - k + 1, 1))}
    sb = {tuple(wb[i : i + k]) for i in range(max(len(wb) - k + 1, 1))}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def latest_report_pair(
    filings: list[dict], as_of: date
) -> tuple[dict, dict] | None:
    """Two most recent same-form periodic reports filed on/before as_of:
    prefer consecutive 10-Qs, fall back to consecutive 10-Ks."""
    as_of_iso = as_of.isoformat()
    for form in ("10-Q", "10-K"):
        matches = [
            f
            for f in filings
            if f["form"] == form
            and f["filingDate"]
            and f["filingDate"] <= as_of_iso
            and f["primaryDocument"]
        ]
        if len(matches) >= 2:
            return matches[0], matches[1]
    return None


def fetch_filing_similarity(
    tickers: list[str],
    client: EdgarClient,
    as_of: date | None = None,
    text_cache: dict[str, str] | None = None,
) -> dict[str, float | None]:
    """Language similarity of each issuer's last two periodic reports.

    `text_cache` (accession -> stripped text) lets the backtest reuse
    documents across rebalance dates.
    """
    as_of = as_of or date.today()
    cache = text_cache if text_cache is not None else {}
    out: dict[str, float | None] = {}
    for t in tickers:
        cik = client.cik_for(t)
        if cik is None:
            out[t] = None
            continue
        try:
            pair = latest_report_pair(client.recent_filings(cik), as_of)
            if pair is None:
                out[t] = None
                continue
            texts = []
            for f in pair:
                key = f["accessionNumber"]
                if key not in cache:
                    cache[key] = strip_html(
                        client.filing_text(cik, key, f["primaryDocument"])
                    )
                texts.append(cache[key])
            out[t] = shingle_similarity(texts[0], texts[1])
        except Exception as exc:  # noqa: BLE001 — per-ticker failures are non-fatal
            log.warning("filing similarity failed for %s: %s", t, exc)
            out[t] = None
    return out
