#!/usr/bin/env python3
"""Is the 90-day insider window too short now that scheduled trades are excluded?

After #39 removed Rule 10b5-1 plan trades from the score, the live run collapsed:
of 63 scored tickers, 33 tied at exactly zero (no discretionary activity at all),
28 scored negative (discretionary selling) and only 2 scored positive. The part
of the signal with literature behind it — insider BUYING — fires for two names,
while the largest weight in the table sorts mostly on selling.

Two candidate explanations, and they imply opposite actions:

  (a) The window is too short. Open-market buys are rare per quarter but common
      per year, so 90 days misses most of them. Lakonishok/Lee and Jeng/Metrick/
      Zeckhauser both work at 6-12 month horizons. Fix: widen the window.

  (b) Small/mid-cap tech insiders simply do not buy on the open market. Then
      widening adds mostly more SELLS, making the signal more negative-dominated
      rather than better, and the honest fix is elsewhere entirely.

Six data points from an earlier diagnostic hint at (b) — every sampled issuer
showed net negative flow and "0 distinct buyers" over 90 days — but six issuers
is not evidence. This measures it across the universe at three window lengths
computed from ONE fetch pass.

COVERAGE WARNING, learned the hard way: fetch_form4_history keeps the NEWEST
filings up to max_filings. A cap too small for the window silently truncates
active filers and biases coverage by filing frequency — that is precisely what
manufactured the insider IC of +0.068 reverted in #24. This uses a generous cap
AND reports every ticker that hits it, so truncation can never be invisible.

    python scripts/diagnose_insider_window.py --limit 40
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
from stock_selector.data_sources.sec_insider import (  # noqa: E402
    fetch_form4_history,
    window_activity,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers-from", default="config/universe.csv")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--windows", default="90,180,365")
    ap.add_argument("--max-filings", type=int, default=400)
    args = ap.parse_args()

    ua = os.environ.get("SEC_EDGAR_USER_AGENT")
    if not ua:
        print("SEC_EDGAR_USER_AGENT not set — cannot query EDGAR")
        return 1

    windows = [int(w) for w in args.windows.split(",")]
    longest = max(windows)
    client = EdgarClient(ua)
    today = date.today()

    with open(args.tickers_from) as fh:
        tickers = [r["ticker"].strip().upper() for r in csv.DictReader(fh)][: args.limit]

    print(f"=== insider window diagnostic — {today} ===")
    print(f"{len(tickers)} tickers, one fetch pass over {longest}d, "
          f"cap {args.max_filings}/ticker\n")

    print("[1] FETCH (watching for cap truncation)")
    histories: dict[str, list[dict]] = {}
    truncated: list[tuple[str, int]] = []
    for t in tickers:
        hist = fetch_form4_history(
            client, t, today - timedelta(days=longest), max_filings=args.max_filings
        )
        if hist is None:
            continue
        histories[t] = hist
        if len(hist) >= args.max_filings:
            truncated.append((t, len(hist)))
    total = sum(len(h) for h in histories.values())
    print(f"  {len(histories)} tickers resolved, {total} Form 4s parsed")
    if truncated:
        print(f"  !! {len(truncated)} TICKERS HIT THE CAP — coverage is biased, "
              f"raise --max-filings: {truncated[:8]}")
    else:
        print(f"  no ticker hit the cap — coverage is complete for {longest}d")

    print("\n[2] DISCRETIONARY ACTIVITY BY WINDOW LENGTH")
    print(f"  {'window':>7}{'w/ BUY':>9}{'w/ SELL':>9}{'silent':>8}"
          f"{'distinct':>10}{'max tie':>9}{'positive':>10}")
    rows = {}
    for w in windows:
        acts = {t: window_activity(h, today, w) for t, h in histories.items()}
        acts = {t: a for t, a in acts.items() if a is not None}
        with_buy = sum(1 for a in acts.values() if a["distinct_buyers"] > 0)
        with_sell = sum(
            1 for a in acts.values()
            if a["sell_dollars"] > 0 and a["signal_dollars"] < 0
        )
        silent = sum(1 for a in acts.values() if a["signal_dollars"] == 0.0)
        positive = sum(1 for a in acts.values() if a["signal_dollars"] > 0)
        vals = Counter(round(a["signal_dollars"], 2) for a in acts.values())
        maxtie = max(vals.values()) if vals else 0
        rows[w] = (with_buy, with_sell, silent, len(vals), maxtie, positive, len(acts))
        print(f"  {w:>7}{with_buy:>9}{with_sell:>9}{silent:>8}"
              f"{len(vals):>10}{maxtie:>9}{positive:>10}")
    n = rows[windows[0]][6]
    print(f"  (n = {n} tickers scored)")

    print("\n[3] HOW MUCH OF THE FLOW IS BUYING AT ALL")
    for w in windows:
        acts = [window_activity(h, today, w) for h in histories.values()]
        acts = [a for a in acts if a is not None]
        buy = sum(a["buy_dollars"] for a in acts)
        sell = sum(a["sell_dollars"] for a in acts)
        planned = sum(a["planned_filings"] for a in acts)
        filings = sum(a["filings"] for a in acts)
        ratio = (buy / sell) if sell else float("inf")
        print(f"  {w:>4}d  buys ${buy:>14,.0f}   sells ${sell:>15,.0f}   "
              f"buy/sell {ratio:>6.3f}   planned {planned}/{filings}")

    print("\n[4] READ THIS AS")
    b90, b_long = rows[windows[0]][0], rows[windows[-1]][0]
    if b_long >= 2 * max(b90, 1) and b_long >= 0.25 * n:
        print(f"  Widening helps: tickers with a discretionary buy go {b90} -> "
              f"{b_long} ({windows[0]}d -> {windows[-1]}d). Explanation (a).")
        print("  A longer window is worth backtesting before adopting.")
    elif b_long <= 1.5 * max(b90, 1):
        print(f"  Widening does NOT help: {b90} -> {b_long} tickers with a buy.")
        print("  Explanation (b) — these insiders rarely buy on the open market")
        print("  at any horizon, so a longer window mostly imports more selling.")
        print("  The sparsity is a property of the universe, not of the window.")
    else:
        print(f"  Mixed: {b90} -> {b_long}. Worth a backtest, not an assumption.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
