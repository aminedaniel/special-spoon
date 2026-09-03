"""Insider (Form 4) activity from SEC EDGAR, scoped to each issuer's own
submissions feed — never full-text search, which would match unrelated
filings for short/common tickers like 'S' or 'U'.

Two consumers:
- the weekly run wants windowed activity in a trailing window;
- the backtest wants the full dated history so it can window any as-of date.
Both share `fetch_form4_history`, which parses each Form 4 XML exactly once.

Scoring follows what the insider-trading literature actually finds, not the
naive net-dollar sum:
- purchases are informative; sales are mostly noise (diversification,
  liquidity, scheduled 10b5-1 plans), so sells are heavily discounted
  rather than allowed to cancel real buys one-for-one;
- officer buys (the people running the company) beat outsider-director buys;
- *cluster* buys — several distinct insiders buying in the same window —
  are the strongest single configuration in the literature;
- trades made under a pre-arranged Rule 10b5-1 plan carry no information and
  are excluded from the score entirely (see below).

Cohen, Malloy & Pomorski (2012), "Decoding Inside Information", found that
insiders trading on a routine schedule have no predictive power, and that
removing them leaves the discretionary traders holding nearly all the signal.
They had to INFER routineness from timing — same calendar month for three
consecutive years — because in 2012 nothing was disclosed. Since April 2023
Form 4 carries a mandatory Rule 10b5-1(c) indicator, which is that fact stated
outright, in a document this module already fetches.

Both routes were measured against live filings before choosing
(scripts/diagnose_insider_plans.py, 824 Form 4s over five issuers):

  aff10b5One            present in 824/824 documents, set true in 385 (47%)
  CMP timing proxy      only 6 of 53 owners classifiable as routine over 3y

So the disclosed flag wins on every axis: it covers every filing rather than a
tenth of the owners, it needs no multi-year history (which would cost roughly
10x the requests the weekly run makes today), and it is a stated fact rather
than an inference. Planned trades are dropped from `signal_dollars` and from
the distinct-buyer cluster count, but stay in the raw buy/sell/net totals so
the honest numbers still reconcile.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import date, timedelta

from .edgar import EdgarClient

log = logging.getLogger(__name__)

# 90 days, not 14. Only open-market codes P/S count (awards, option exercises
# and tax withholding are excluded as noise), and those are rare enough in
# small-cap tech that a fortnight leaves *every* ticker at exactly zero — a
# constant column that ranks nothing. A quarter is also the horizon the
# insider-buying literature uses, and it matches the "last 60 days" insider
# review in the weekly deep dive.
LOOKBACK_DAYS = 90
MAX_FILINGS_PER_TICKER = 40   # weekly-run bound; a quarter holds more Form 4s
MAX_HISTORY_FILINGS = 80      # backtest bound (years of Form 4s for a small cap)

OFFICER_BUY_WEIGHT = 2.0      # buys by the people running the company
BASE_BUY_WEIGHT = 1.0         # directors / 10% owners
SELL_DISCOUNT = 0.25          # sales are mostly noise; don't let them cancel buys 1:1
CLUSTER_STEP = 0.25           # per extra distinct buyer beyond the first
CLUSTER_CAP_BUYERS = 5        # multiplier saturates at 2.0 (five distinct buyers)

# Rule 10b5-1(c) indicator, mandatory on Form 4 since April 2023. Measured at
# 47% of live filings, so this excludes roughly half the transactions from the
# score — which is the point: they were decided months before they executed.
PLAN_FLAG_PATH = ".//aff10b5One"


def _flag(root: ET.Element, path: str) -> bool:
    v = (root.findtext(path) or "").strip().lower()
    return v in ("1", "true")


def parse_form4(xml_text: str) -> dict:
    """One Form 4's open-market activity plus who filed it.

    Only transaction codes P (open-market purchase) and S (open-market sale)
    count — awards, option exercises, tax withholding, and gifts are excluded.
    Returns {buy, sell, owner_cik, is_officer, is_director, is_planned}.

    `is_planned` is the Form 4 Rule 10b5-1(c) checkbox. Live filings encode it
    as both "1"/"0" and "true"/"false"; _flag handles both.
    """
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

    owner = root.find("reportingOwner")
    owner_cik = None
    is_officer = is_director = False
    if owner is not None:
        owner_cik = (owner.findtext("reportingOwnerId/rptOwnerCik") or "").strip() or None
        is_officer = _flag(owner, "reportingOwnerRelationship/isOfficer")
        is_director = _flag(owner, "reportingOwnerRelationship/isDirector")
    return {
        "buy": buy,
        "sell": sell,
        "owner_cik": owner_cik,
        "is_officer": is_officer,
        "is_director": is_director,
        "is_planned": _flag(root, PLAN_FLAG_PATH),
    }


def fetch_form4_history(
    client: EdgarClient,
    ticker: str,
    since: date,
    max_filings: int = MAX_FILINGS_PER_TICKER,
) -> list[dict] | None:
    """Dated Form 4 records for the issuer since `since`, newest first.
    None when the ticker can't be resolved or EDGAR fails. A filing whose
    XML can't be fetched/parsed contributes a zero-dollar record."""
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

    out: list[dict] = []
    for f in form4s:
        record = {
            "buy": 0.0, "sell": 0.0,
            "owner_cik": None, "is_officer": False, "is_director": False,
            # An unparseable filing is not evidence of a plan; never let a
            # fetch failure silently discard a real discretionary trade.
            "is_planned": False,
        }
        if f["primaryDocument"].endswith(".xml"):
            try:
                xml_text = client.filing_text(
                    cik, f["accessionNumber"], f["primaryDocument"]
                )
                record = parse_form4(xml_text)
            except Exception as exc:  # noqa: BLE001 — skip unparseable filings
                log.debug(
                    "Form 4 parse failed for %s %s: %s",
                    ticker,
                    f["accessionNumber"],
                    exc,
                )
        record["date"] = date.fromisoformat(f["filingDate"])
        out.append(record)
    return out


def window_activity(
    history: list[dict] | None, as_of: date, lookback_days: int
) -> dict | None:
    """Aggregate a Form 4 history over (as_of - lookback, as_of].

    `signal_dollars` is what the signal ranks, and it is built from
    DISCRETIONARY trades only: officer buys weighted OFFICER_BUY_WEIGHT, other
    buys BASE_BUY_WEIGHT, the total scaled up when several *distinct* insiders
    bought (cluster effect, capped at 2x), minus sells discounted to
    SELL_DISCOUNT so ordinary selling can't cancel a real buy cluster
    one-for-one.

    Trades executed under a pre-arranged Rule 10b5-1 plan are excluded from the
    score and from the cluster count: they were decided months before they
    executed, so they say nothing about what the insider believes today. Note
    the sign consequence — dropping planned SELLS raises the score for issuers
    whose insiders sell on schedule. That is the intended correction, not a
    side effect: a scheduled sale is not evidence of anything.

    The raw totals (`buy_dollars`, `sell_dollars`, `net_dollars`) still count
    every trade, planned or not, so the honest numbers reconcile against EDGAR.
    `planned_filings` reports how much of the window was excluded.
    """
    if history is None:
        return None
    start = as_of - timedelta(days=lookback_days)
    in_window = [r for r in history if start < r["date"] <= as_of]
    # .get(): records predating the 10b5-1 flag, and those from filings that
    # failed to parse, are treated as discretionary rather than dropped.
    discretionary = [r for r in in_window if not r.get("is_planned", False)]

    buy_total = sum(r["buy"] for r in in_window)
    sell_total = sum(r["sell"] for r in in_window)
    discretionary_sells = sum(r["sell"] for r in discretionary)
    weighted_buys = sum(
        r["buy"] * (OFFICER_BUY_WEIGHT if r["is_officer"] else BASE_BUY_WEIGHT)
        for r in discretionary
    )
    buyers = {
        r["owner_cik"] for r in discretionary if r["buy"] > 0 and r["owner_cik"]
    }
    cluster_mult = 1.0 + CLUSTER_STEP * min(
        max(len(buyers) - 1, 0), CLUSTER_CAP_BUYERS - 1
    )
    return {
        "signal_dollars": (
            weighted_buys * cluster_mult - SELL_DISCOUNT * discretionary_sells
        ),
        "net_dollars": buy_total - sell_total,
        "buy_dollars": buy_total,
        "sell_dollars": sell_total,
        "distinct_buyers": len(buyers),
        "filings": len(in_window),
        "planned_filings": len(in_window) - len(discretionary),
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
