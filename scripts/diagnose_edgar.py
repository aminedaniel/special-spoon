#!/usr/bin/env python3
"""Answer two questions about what EDGAR actually returns, using live data.

1. Does an issuer's own submissions feed contain SC 13D/13G filings? Those are
   filed *by the beneficial owner*, with the issuer only as subject company, so
   the events signal may be looking for filings that are structurally absent
   from the feed it reads. If so the signal can never fire on stakes.
2. How many open-market Form 4s (codes P/S) fall in a 14-day vs 90-day window?
   The weekly run scored every ticker identically on insider activity, which
   only happens when the window is empty for all of them.

Run in CI where SEC is reachable: python scripts/diagnose_edgar.py
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stock_selector.data_sources.edgar import EdgarClient  # noqa: E402
from stock_selector.data_sources.sec_insider import (  # noqa: E402
    fetch_form4_history,
)

STAKE_FORMS = {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tickers", default="RNG,QLYS,DBX,GEN,PRGS,CRTO,YELP,TENB,BOX,FIVN"
    )
    args = parser.parse_args()

    ua = os.environ.get("SEC_EDGAR_USER_AGENT")
    if not ua:
        print("SEC_EDGAR_USER_AGENT not set — cannot query EDGAR")
        return 1

    client = EdgarClient(ua)
    today = date.today()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    print(f"=== EDGAR diagnostic — {today} ===\n")

    stake_total = Counter()
    for t in tickers:
        cik = client.cik_for(t)
        if cik is None:
            print(f"{t}: no CIK resolved")
            continue
        filings = client.recent_filings(cik)
        forms = Counter(f["form"] for f in filings)
        stakes = {f: n for f, n in forms.items() if f in STAKE_FORMS}
        stake_total.update(stakes)

        oldest = min((f["filingDate"] for f in filings if f["filingDate"]), default="?")
        print(f"{t} (CIK {cik}): {len(filings)} filings, oldest {oldest}")
        print(f"   stake forms present: {stakes or 'NONE'}")
        print(f"   S-3: {forms.get('S-3', 0)}   8-K: {forms.get('8-K', 0)}   "
              f"Form 4: {forms.get('4', 0)}")

        # Insider: 14-day vs 90-day open-market activity.
        hist = fetch_form4_history(client, t, today - timedelta(days=90), max_filings=40)
        if hist is None:
            print("   Form 4 history: unavailable")
            continue
        for days in (14, 90):
            start = today - timedelta(days=days)
            win = [(d, n) for d, n in hist if start < d <= today]
            nonzero = [n for _, n in win if n != 0.0]
            print(f"   {days:>2}d window: {len(win)} Form 4s, "
                  f"{len(nonzero)} with open-market $ , net ${sum(nonzero):,.0f}")
        print()

    print("=== VERDICT ===")
    if stake_total:
        print(f"Stake filings DO appear in issuer feeds: {dict(stake_total)}")
        print("-> events signal can fire; its zeros were genuine, not structural.")
    else:
        print("NO SC 13D/13G in any issuer feed.")
        print("-> confirms the events signal cannot see stakes from this endpoint;")
        print("   only S-3 shelves and 8-K 4.02 can ever score.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
