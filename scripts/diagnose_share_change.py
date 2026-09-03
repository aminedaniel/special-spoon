#!/usr/bin/env python3
"""What does get_shares_full actually return, and how badly do splits break it?

fetch_share_change scores dilution as shares.iloc[-1] / shares.iloc[0] - 1 over
raw, unadjusted share counts. Nothing in that path adjusts for stock splits, so
a 2:1 split doubles the count and is read as +100% dilution — the WORST possible
rank on that sub-signal — while a reverse split reads as a huge buyback and
ranks best. That is live today, at an effective 0.045 of the composite.

Before fixing it, four things need measuring rather than assuming:

  [2] the shape of the series — irregular step function, tz-aware index, how
      many observations, how far back the first one really is (the code treats
      iloc[0] as "a year ago" without checking)
  [3] which jumps are splits, cross-checked against yf.Ticker(t).splits, so the
      fix keys on real corporate actions rather than a jump heuristic
  [4] the LIVE DAMAGE: for tickers that split in the trailing 13 months, what
      dilution figure does production compute for them right now
  [5] whether the index dates are PERIOD ENDS or FILING DATES. This decides the
      reporting lag needed to backtest issuance without lookahead, and guessing
      it would put lookahead into the one fundamentals-family signal that can
      otherwise be measured honestly.

Writes nothing, changes nothing.

    python scripts/diagnose_share_change.py --limit 40 --years 4
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yfinance as yf  # noqa: E402

LIVE_LOOKBACK_DAYS = 365          # what fetch_share_change uses today
SPLIT_TOLERANCE = 0.05            # how close a jump must be to n or 1/n


def suspected_split(ratio: float) -> str | None:
    """Label a consecutive-observation ratio that looks like a split."""
    if ratio <= 0:
        return None
    for n in range(2, 21):
        if abs(ratio - n) / n <= SPLIT_TOLERANCE:
            return f"{n}:1"
        if abs(ratio - 1.0 / n) * n <= SPLIT_TOLERANCE:
            return f"1:{n}"
    return None


def quarter_end_distance(d: date) -> int:
    """Days from d to the nearest calendar quarter end — small means the index
    is dated by period end (needs a reporting lag), large means filing date."""
    ends = [date(d.year - 1, 12, 31), date(d.year, 3, 31), date(d.year, 6, 30),
            date(d.year, 9, 30), date(d.year, 12, 31)]
    return min(abs((d - e).days) for e in ends)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers-from", default="config/universe.csv")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--years", type=float, default=4.0)
    args = ap.parse_args()

    today = date.today()
    start = today - timedelta(days=int(365 * args.years))
    with open(args.tickers_from) as fh:
        tickers = [r["ticker"].strip().upper() for r in csv.DictReader(fh)][: args.limit]

    print(f"=== share-count diagnostic — {today} ===")
    print(f"{len(tickers)} tickers, history from {start} ({args.years}y)\n")

    series: dict[str, object] = {}
    too_short, failed = [], []
    for t in tickers:
        try:
            s = yf.Ticker(t).get_shares_full(start=start.isoformat())
        except Exception as exc:  # noqa: BLE001 — reporting the failure IS the result
            failed.append((t, f"{type(exc).__name__}: {exc}"))
            continue
        if s is None or len(s.dropna()) < 2:
            too_short.append(t)
            continue
        series[t] = s.dropna()

    print("[1] COVERAGE  (production omits both of the last two silently)")
    print(f"  usable        {len(series)}/{len(tickers)}")
    print(f"  <2 points     {len(too_short)}  {too_short[:10]}")
    print(f"  fetch failed  {len(failed)}  {[f[0] for f in failed][:10]}")
    for t, e in failed[:3]:
        print(f"      {t}: {e}")
    if not series:
        print("\nNothing usable — cannot answer anything else.")
        return 0

    print("\n[2] SERIES SHAPE")
    counts, first_lags, gaps = [], [], []
    idx_kinds: Counter = Counter()
    for t, s in series.items():
        counts.append(len(s))
        idx_kinds[f"{type(s.index).__name__} tz={getattr(s.index, 'tz', None)}"] += 1
        dates = [d.date() if hasattr(d, "date") else d for d in s.index]
        first_lags.append((today - dates[0]).days)
        gaps.extend((b - a).days for a, b in zip(dates, dates[1:]))
    print(f"  index types: {dict(idx_kinds)}")
    print(f"  observations/ticker: min {min(counts)} median "
          f"{int(statistics.median(counts))} max {max(counts)}")
    print(f"  first observation is N days old: min {min(first_lags)} median "
          f"{int(statistics.median(first_lags))} max {max(first_lags)}")
    if gaps:
        gaps.sort()
        print(f"  gap between observations (days): median {gaps[len(gaps)//2]}, "
              f"p90 {gaps[int(len(gaps)*0.9)]}, max {gaps[-1]}")
    print("  NOTE: production assumes iloc[0] is ~1y old. Spread above says how")
    print("        far that assumption drifts per ticker.")

    print("\n[3] SPLIT DETECTION (jump heuristic vs the actual .splits feed)")
    heuristic: dict[str, list] = {}
    for t, s in series.items():
        vals = list(s.values)
        dates = [d.date() if hasattr(d, "date") else d for d in s.index]
        for i in range(1, len(vals)):
            if vals[i - 1] <= 0:
                continue
            lbl = suspected_split(vals[i] / vals[i - 1])
            if lbl:
                heuristic.setdefault(t, []).append((dates[i], lbl,
                                                    vals[i - 1], vals[i]))
    print(f"  tickers with a suspected split jump: {len(heuristic)}")
    for t, evs in list(heuristic.items())[:8]:
        for d, lbl, a, b in evs[:2]:
            print(f"    {t:<6} {d}  {lbl:<5} {a:,.0f} -> {b:,.0f}")

    confirmed = {}
    for t in series:
        try:
            sp = yf.Ticker(t).splits
            if sp is not None and len(sp):
                recent = {(d.date() if hasattr(d, "date") else d): float(r)
                          for d, r in sp.items()
                          if (d.date() if hasattr(d, "date") else d) >= start}
                if recent:
                    confirmed[t] = recent
        except Exception:  # noqa: BLE001
            pass
    print(f"  tickers with a real split in .splits: {len(confirmed)}")
    for t, ev in list(confirmed.items())[:8]:
        print(f"    {t:<6} {ev}")
    print(f"  agreement: heuristic {sorted(heuristic)} vs feed {sorted(confirmed)}")
    print("  -> if .splits is reliable here, key the fix on it, not on the jump test")

    print("\n[4] LIVE DAMAGE — what production computes TODAY for these tickers")
    cutoff = today - timedelta(days=LIVE_LOOKBACK_DAYS + 30)
    affected = set(heuristic) | set(confirmed)
    if not affected:
        print("  no split in window for this sample — the bug is latent here,")
        print("  which is not the same as absent. Re-run on a wider sample.")
    else:
        print(f"  {'ticker':<8}{'dilution as scored':>20}   reading")
        for t in sorted(affected):
            s = series[t]
            dates = [d.date() if hasattr(d, "date") else d for d in s.index]
            win = [v for d, v in zip(dates, s.values) if d >= cutoff]
            if len(win) < 2:
                continue
            change = win[-1] / win[0] - 1.0
            note = ("SPURIOUS DILUTION — ranks worst" if change > 0.3 else
                    "SPURIOUS BUYBACK — ranks best" if change < -0.3 else
                    "plausible")
            print(f"  {t:<8}{change:>19.1%}   {note}")

    print("\n[5] ARE INDEX DATES PERIOD ENDS OR FILING DATES?")
    print("     (decides the reporting lag needed to backtest without lookahead)")
    dists = []
    for s in series.values():
        for d in s.index:
            dd = d.date() if hasattr(d, "date") else d
            dists.append(quarter_end_distance(dd))
    dists.sort()
    med = dists[len(dists) // 2]
    near = sum(1 for x in dists if x <= 5) / len(dists)
    print(f"  distance to nearest quarter end: median {med}d, "
          f"{100*near:.0f}% within 5 days")
    if near > 0.5:
        print("  -> PERIOD ENDS. A reporting lag (~45d) is REQUIRED for the")
        print("     backtest, or it reads share counts before they were public.")
    else:
        print("  -> not clustered on quarter ends; likely update/filing dates.")
        print("     A smaller lag may suffice — size it from this distribution.")

    print("\n[6] READ THIS AS")
    print(f"  Splits: {len(confirmed)} confirmed, {len(heuristic)} by heuristic.")
    print("  Fix keys on the .splits feed where available, heuristic as backstop.")
    print(f"  Coverage: {len(too_short) + len(failed)} tickers produce nothing and")
    print("  today vanish without a log line — that is the #24 failure mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
