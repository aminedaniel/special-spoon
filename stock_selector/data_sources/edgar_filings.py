"""Corporate-event flags and filing-language similarity from EDGAR.

Events (point-in-time from the submissions feed, no document fetches):
  +2    SC 13D / 13D/A      activist stake with intent to influence (capped:
                            presence, not count — see below)
  -1    S-3 family          shelf registration (dilution risk)
  -2    8-K with item 4.02  previously issued financials can't be relied on
  -0.5  8-K dumped Friday after hours / weekend (news-timing red flag)

Two things here were measured, not assumed (scripts/diagnose_events.py over
the live 99-ticker universe, 4210 stake filings):

1. The stake window is 365 days, not 120, because 13-series filings are
   ANNUAL, not uniform. Filings by calendar month: Feb 2612, Jan 590, Nov 250,
   every other month 65-110. Schedule 13G amendments are due within 45 days of
   year end, so 62% of all stake filings land in February. A 120-day window
   ending anywhere in Jun-Dec therefore cannot see a single one: the live run
   found NONE in window across all 93 resolved tickers, and 90% of the universe
   scored exactly 0.0. The signal was seasonally blind for most of the year.

2. The 13G family is NOT scored at all, despite being 94% of stake filings
   (SC 13G/A 3011, SC 13G 948, vs SC 13D/A 205, SC 13D 46). 13G is the passive
   >5% crossing that every index fund files; over a 365-day window essentially
   every issuer has one, so scoring it adds the same constant to every ticker
   and cannot reorder anything — the same inert-scalar reason macro stays
   unweighted. Counting them instead would proxy institutional breadth, which
   is a size effect, not alpha. Only 13D — the activist form, and the one with
   documented abnormal returns (Brav/Jiang/Partnoy/Thomas 2008) — is scored.

Activist points are flat rather than additive: 13D/A amendments outnumber
initial 13Ds 4:1, so summing them would let one long-running campaign accrue
an unbounded score. Presence of an activist situation is the signal; the
number of amendments filed about it is not.

The shelf match covers the whole family — the live diagnostic found zero
plain "S-3" strings across nine issuers' decade-long feeds because real
filers use the variants: S-3ASR (well-known seasoned issuers' automatic
shelves), S-3MEF, and F-3/F-3ASR for foreign private issuers.

The Friday flag is the disclosure-timing effect (deHaan/Shevlin/Thornock):
managers strategically file bad news when nobody is watching — after the
close on Friday or on weekends — and the market underreacts to it.

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

ACTIVIST_WINDOW_DAYS = 365   # 13-series filings cluster in February — see docstring
SHELF_WINDOW_DAYS = 120
REDFLAG_WINDOW_DAYS = 60

# Only the activist family scores. The passive 13G family is deliberately
# absent — it is 94% of stake filings and near-universal, so it cannot rank.
ACTIVIST_FORMS = {"SC 13D", "SC 13D/A"}
ACTIVIST_POINTS = 2.0        # flat if any in window, never summed
# The whole shelf family, not just plain S-3 — see module docstring.
SHELF_FORMS = {"S-3", "S-3/A", "S-3ASR", "S-3MEF", "F-3", "F-3/A", "F-3ASR"}
SHELF_POINTS = -1.0
QUIET_DUMP_POINTS = -0.5   # 8-K accepted Friday post-16:00 ET or on a weekend
_ACCEPT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})")


def is_quiet_dump(acceptance: str | None) -> bool:
    """True when an acceptanceDateTime lands Friday after 16:00 ET or on a
    weekend — the classic burying-the-news slot.

    EDGAR acceptance stamps are US-Eastern wall-clock time, so no timezone
    math is needed. Malformed/missing stamps are False (no evidence).
    """
    if not acceptance:
        return False
    m = _ACCEPT_RE.match(acceptance)
    if not m:
        return False
    try:
        d = date.fromisoformat(m.group(1))
    except ValueError:
        return False
    weekday, hour = d.weekday(), int(m.group(2))
    return weekday >= 5 or (weekday == 4 and hour >= 16)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
SHINGLE_WORDS = 5


def event_points(
    filings: list[dict], as_of: date
) -> float:
    """Sum event points for filings inside each event type's window.

    Activist presence contributes a single flat ACTIVIST_POINTS regardless of
    how many 13D/13D/A filings fall in the window; the negatives still sum.
    """
    activist_cutoff = (as_of - timedelta(days=ACTIVIST_WINDOW_DAYS)).isoformat()
    shelf_cutoff = (as_of - timedelta(days=SHELF_WINDOW_DAYS)).isoformat()
    redflag_cutoff = (as_of - timedelta(days=REDFLAG_WINDOW_DAYS)).isoformat()
    as_of_iso = as_of.isoformat()

    points = 0.0
    has_activist = False
    for f in filings:
        filed = f["filingDate"]
        if not filed or filed > as_of_iso:
            continue
        form = f["form"]
        if form in ACTIVIST_FORMS and filed >= activist_cutoff:
            has_activist = True
        elif form in SHELF_FORMS and filed >= shelf_cutoff:
            points += SHELF_POINTS
        elif form == "8-K" and filed >= redflag_cutoff:
            if "4.02" in (f["items"] or ""):
                points -= 2.0
            if is_quiet_dump(f.get("acceptanceDateTime")):
                points += QUIET_DUMP_POINTS
    if has_activist:
        points += ACTIVIST_POINTS
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
