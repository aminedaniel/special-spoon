#!/usr/bin/env python3
"""What does a real Form 4 actually tell us about *scheduled* trading?

Cohen, Malloy & Pomorski (2012) found that insiders who trade on a routine
schedule carry no predictive power, and that stripping them out leaves the
"opportunistic" traders holding nearly all the signal. Our insider signal
(the largest weight in the table, 0.14) does not make that distinction.

CMP had to INFER routineness from timing — trading the same calendar month
for several consecutive years — because in 2012 nothing was disclosed. Since
April 2023 Form 4 carries a mandatory checkbox for Rule 10b5-1(c) trading
arrangements: the exact fact their proxy approximated, stated outright, in a
document this pipeline already fetches for every filing in the 90-day window.

So before building anything, this measures which of the two is actually
available, because guessing the schema is how the last three bugs happened:

  [2] every distinct XML tag in the sample, so the schema is observed
  [3] any 10b5-1 style flag, how often it is set, and what values it takes
  [4] footnote text mentioning 10b5-1 — the pre-2023 disclosure route, and
      still where many filers put plan-adoption dates
  [5] whether CMP's timing classification is even feasible on the history
      depth this pipeline can afford to fetch

Writes nothing, scores nothing.

    python scripts/diagnose_insider_plans.py --tickers RNG,DBX,YELP --years 3
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stock_selector.data_sources.edgar import EdgarClient  # noqa: E402

PLAN_TAG_RE = re.compile(r"10b5|rule10|plan|arrang", re.I)
PLAN_TEXT_RE = re.compile(r"10b5-?1", re.I)
TRUE_VALUES = {"1", "true"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="RNG,DBX,YELP,CRTO,PRGS")
    ap.add_argument("--years", type=float, default=3.0)
    ap.add_argument("--max-per-ticker", type=int, default=180)
    args = ap.parse_args()

    ua = os.environ.get("SEC_EDGAR_USER_AGENT")
    if not ua:
        print("SEC_EDGAR_USER_AGENT not set — cannot query EDGAR")
        return 1

    client = EdgarClient(ua)
    today = date.today()
    cutoff = (today - timedelta(days=int(365 * args.years))).isoformat()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    tag_census: Counter = Counter()
    plan_tag_values: dict[str, Counter] = defaultdict(Counter)
    footnote_hits = 0
    parsed = 0
    fetched = 0
    # owner_cik -> list of (year, month) for open-market trades
    owner_months: dict[str, list[tuple[int, int]]] = defaultdict(list)
    owner_names: dict[str, str] = {}

    print(f"=== Form 4 schema / scheduling diagnostic — {today} ===")
    print(f"window: filings since {cutoff} ({args.years}y), "
          f"cap {args.max_per_ticker}/ticker\n")

    print("[1] SAMPLE")
    for t in tickers:
        cik = client.cik_for(t)
        if cik is None:
            print(f"  {t}: no CIK")
            continue
        filings = client.recent_filings(cik)
        f4 = [f for f in filings
              if f["form"] == "4" and f["filingDate"] >= cutoff][: args.max_per_ticker]
        oldest = min((f["filingDate"] for f in f4), default="-")
        print(f"  {t:<6} {len(f4):>4} Form 4s since {oldest}")

        for f in f4:
            if not f["primaryDocument"].endswith(".xml"):
                continue
            fetched += 1
            try:
                xml_text = client.filing_text(
                    cik, f["accessionNumber"], f["primaryDocument"]
                )
                root = ET.fromstring(xml_text)
            except Exception:  # noqa: BLE001 — unparseable filings just don't count
                continue
            parsed += 1

            for el in root.iter():
                tag_census[el.tag] += 1
                if PLAN_TAG_RE.search(el.tag):
                    plan_tag_values[el.tag][(el.text or "").strip()[:20]] += 1

            if PLAN_TEXT_RE.search(xml_text):
                footnote_hits += 1

            # CMP feasibility: which owners trade open-market, and when
            owner = root.find("reportingOwner")
            ocik = None
            if owner is not None:
                ocik = (owner.findtext("reportingOwnerId/rptOwnerCik") or "").strip()
                nm = (owner.findtext("reportingOwnerId/rptOwnerName") or "").strip()
                if ocik:
                    owner_names[ocik] = nm
            has_open_market = any(
                tx.findtext("transactionCoding/transactionCode") in ("P", "S")
                for tx in root.iter("nonDerivativeTransaction")
            )
            if ocik and has_open_market:
                d = date.fromisoformat(f["filingDate"])
                owner_months[ocik].append((d.year, d.month))

    print(f"\n  fetched {fetched}, parsed {parsed}")
    if not parsed:
        print("  nothing parsed — cannot answer anything else")
        return 0

    print(f"\n[2] TAG CENSUS ({len(tag_census)} distinct tags)")
    for tag, n in tag_census.most_common(40):
        print(f"  {n:>6}  {tag}")

    print("\n[3] 10b5-1 / PLAN-STYLE TAGS")
    if plan_tag_values:
        for tag, vals in sorted(plan_tag_values.items()):
            total = sum(vals.values())
            set_true = sum(n for v, n in vals.items() if v.lower() in TRUE_VALUES)
            print(f"  {tag}: present in {total} docs, set-true in {set_true}")
            for v, n in vals.most_common(5):
                print(f"      value {v!r}: {n}")
    else:
        print("  NONE — no tag name matches 10b5/rule/plan/arrangement")

    print("\n[4] FOOTNOTE / FREE-TEXT MENTIONS OF 10b5-1")
    print(f"  {footnote_hits}/{parsed} documents ({100*footnote_hits/parsed:.0f}%) "
          f"mention 10b5-1 anywhere in the XML")

    print("\n[5] CMP TIMING-CLASSIFICATION FEASIBILITY")
    print("  CMP call an insider ROUTINE if they traded in the same calendar")
    print("  month for >=3 consecutive years. Needs multi-year history per owner.")
    traders = {o: ms for o, ms in owner_months.items() if ms}
    print(f"  distinct owners with open-market trades: {len(traders)}")
    dist = Counter(len(ms) for ms in traders.values())
    print(f"  trades per owner: " +
          ", ".join(f"{k}x{v}" for k, v in sorted(dist.items())[:10]))
    routine = []
    for o, ms in traders.items():
        by_month = defaultdict(set)
        for y, m in ms:
            by_month[m].add(y)
        for m, years in by_month.items():
            ys = sorted(years)
            run = best = 1
            for a, b in zip(ys, ys[1:]):
                run = run + 1 if b == a + 1 else 1
                best = max(best, run)
            if best >= 3:
                routine.append((o, m, best))
                break
    print(f"  owners classifiable as ROUTINE on this history: {len(routine)}")
    for o, m, run in routine[:8]:
        print(f"      {owner_names.get(o, o)[:28]:<28} month {m:>2}, {run}y run")

    print("\n[6] READ THIS AS")
    has_flag = any(
        sum(n for v, n in vals.items() if v.lower() in TRUE_VALUES) > 0
        for vals in plan_tag_values.values()
    )
    if has_flag:
        print("  A real 10b5-1 flag exists in the XML we already fetch. Use it:")
        print("  it is the disclosed fact CMP's timing proxy was approximating,")
        print("  costs no extra requests, and needs no multi-year history.")
    elif footnote_hits > 0.1 * parsed:
        print("  No structured flag, but free text mentions 10b5-1 often enough")
        print("  to be worth a text match — cheaper than multi-year history.")
    else:
        print("  Neither route is available from the documents we fetch. CMP's")
        print("  timing classification would need the multi-year history in [5],")
        print("  which costs roughly years x filings extra requests per ticker.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
