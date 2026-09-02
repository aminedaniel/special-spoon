#!/usr/bin/env python3
"""Why does the events signal score ~87% of the shortlist identically?

Run 3 of diagnose_edgar.py disproved the standing hypothesis: SC 13D/13G DO
appear in the issuer's own submissions feed (443 of them across 10 issuers),
with form strings matching the scorer's exactly. So the signal can see stakes.

Yet the 2026-08-31 report scored 55 of 63 tickers at the identical mid-rank,
and every differentiated name scored BELOW it -- meaning only the negative
branches (shelf, 8-K 4.02, quiet dump) have ever fired.

At ~1-2 stake filings per issuer per 120 days, chance alone would leave ~22%
of tickers at zero, not 87%. This measures what is actually suppressing them.
The leading hypothesis is seasonality: Schedule 13G amendments were due within
45 days of year end, so the filings should pile up in February -- and a 120-day
window ending 31 August misses that pile entirely.

Reads submissions feeds only (no document fetches), so it is fast.

    python scripts/diagnose_events.py --tickers-from config/universe.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stock_selector.data_sources.edgar import EdgarClient  # noqa: E402
from stock_selector.data_sources.edgar_filings import (  # noqa: E402
    ACTIVIST_FORMS,
    ACTIVIST_WINDOW_DAYS,
    REDFLAG_WINDOW_DAYS,
    SHELF_FORMS,
    SHELF_WINDOW_DAYS,
    event_points,
    is_quiet_dump,
)

# The full 13-series, including the passive 13G family that is no longer
# scored — the histogram must still show it to justify the exclusion.
ALL_STAKE_FORMS = ACTIVIST_FORMS | {"SC 13G", "SC 13G/A"}

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def load_tickers(path: Path) -> list[str]:
    with path.open() as fh:
        return [r["ticker"].strip().upper() for r in csv.DictReader(fh)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers-from", default="config/universe.csv")
    ap.add_argument("--limit", type=int, default=99)
    ap.add_argument("--show", type=int, default=25, help="per-ticker rows to print")
    args = ap.parse_args()

    ua = os.environ.get("SEC_EDGAR_USER_AGENT")
    if not ua:
        print("SEC_EDGAR_USER_AGENT not set — cannot query EDGAR")
        return 1

    client = EdgarClient(ua)
    today = date.today()
    tickers = load_tickers(Path(args.tickers_from))[: args.limit]
    stake_cutoff = today - timedelta(days=ACTIVIST_WINDOW_DAYS)

    print(f"=== events diagnostic — {today} ===")
    print(f"windows: stake {ACTIVIST_WINDOW_DAYS}d (>= {stake_cutoff}), "
          f"shelf {SHELF_WINDOW_DAYS}d, redflag {REDFLAG_WINDOW_DAYS}d\n")

    month_hist: Counter = Counter()          # stake filings by calendar month
    form_hist: Counter = Counter()           # stake filings by form, all time
    in_window_forms: Counter = Counter()     # stake filings inside the window
    points_hist: Counter = Counter()         # resulting event_points
    rows: list[tuple] = []
    no_cik = 0

    for t in tickers:
        cik = client.cik_for(t)
        if cik is None:
            no_cik += 1
            continue
        try:
            filings = client.recent_filings(cik)
        except Exception as exc:  # noqa: BLE001 — diagnostic wants the error
            print(f"  {t}: fetch failed {type(exc).__name__}: {exc}")
            continue

        stakes_all, stakes_win, shelves_win, flags_win = 0, 0, 0, 0
        for f in filings:
            form, filed = f["form"], f["filingDate"]
            if not filed:
                continue
            if form in ALL_STAKE_FORMS:
                stakes_all += 1
                form_hist[form] += 1
                month_hist[int(filed[5:7])] += 1
                if filed >= stake_cutoff.isoformat():
                    stakes_win += 1
                    in_window_forms[form] += 1
            elif form in SHELF_FORMS and filed >= (
                today - timedelta(days=SHELF_WINDOW_DAYS)
            ).isoformat():
                shelves_win += 1
            elif form == "8-K" and filed >= (
                today - timedelta(days=REDFLAG_WINDOW_DAYS)
            ).isoformat():
                if "4.02" in (f["items"] or "") or is_quiet_dump(
                    f.get("acceptanceDateTime")
                ):
                    flags_win += 1

        pts = event_points(filings, today)
        points_hist[pts] += 1
        rows.append((t, stakes_all, stakes_win, shelves_win, flags_win, pts))

    print(f"[1] PER-TICKER (first {args.show} of {len(rows)} resolved; "
          f"{no_cik} unresolved CIKs)")
    print(f"  {'tkr':<7}{'stakes_all':>11}{'in_win':>8}{'shelf':>7}{'8Kflag':>8}{'points':>8}")
    for r in rows[: args.show]:
        print(f"  {r[0]:<7}{r[1]:>11}{r[2]:>8}{r[3]:>7}{r[4]:>8}{r[5]:>8.1f}")

    print(f"\n[2] STAKE FILINGS BY CALENDAR MONTH (all history, {sum(month_hist.values())} filings)")
    print("     tests the seasonality hypothesis — a February pile means a")
    print("     120-day window ending in August structurally cannot see them")
    peak = max(month_hist.values()) if month_hist else 1
    for m in range(1, 13):
        n = month_hist.get(m, 0)
        bar = "#" * int(40 * n / peak) if peak else ""
        print(f"  {MONTHS[m-1]}  {n:>5}  {bar}")

    print(f"\n[3] STAKE FORMS: all-time {dict(form_hist)}")
    print(f"    inside the {ACTIVIST_WINDOW_DAYS}d window: {dict(in_window_forms) or 'NONE'}")

    print("\n[4] RESULTING event_points DISTRIBUTION")
    total = sum(points_hist.values())
    for pts in sorted(points_hist):
        n = points_hist[pts]
        print(f"  {pts:>7.1f}  x{n:>3}  ({100*n/total:.0f}%)")
    zero = points_hist.get(0.0, 0)
    print(f"\n  exactly 0.0: {zero}/{total} ({100*zero/total:.0f}%)")

    print("\n[5] READ THIS AS")
    if month_hist and month_hist.get(2, 0) > 0.3 * sum(month_hist.values()):
        print("  Stake filings pile up in February -> the 120d window is")
        print("  seasonally blind for most of the year. Widening the stake")
        print("  window to ~365d would let 13G crossings actually register.")
    elif sum(in_window_forms.values()) == 0:
        print("  Stakes exist historically but NONE fall in the current window,")
        print("  and they are not February-clustered — look at window length.")
    else:
        print("  Stakes DO fall in the window and do score. The flatness comes")
        print("  from somewhere else — compare [1] against the report column.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
