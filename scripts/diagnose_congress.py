#!/usr/bin/env python3
"""Does congressional trading data actually cover this universe?

The congress signal was removed in #12 on the argument that its feed was dead
and its 30-45 day disclosure lag made it useless. The lag argument is weak --
the insider signal carries the largest weight in the table on a 90-day window,
so a 45-day-old congressional buy cannot be disqualified by staleness alone.
The argument that would actually settle it is coverage: members of Congress
trade mega-caps, and this universe is $300M-$20B. If only a handful of the 99
names ever appear, the column is empty or near-constant and the degenerate
guard drops it anyway -- the removal stands. If thirty appear, the signal
deserves a real backtest and the removal was wrong on the merits.

This writes nothing and scores nothing. It counts.

Run in CI, where the S3 feeds are reachable:
    python scripts/diagnose_congress.py --lookback-days 365
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent

FEEDS = {
    "senate": (
        "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/"
        "aggregate/all_transactions.json"
    ),
    "house": (
        "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/"
        "data/all_transactions.json"
    ),
}

# transaction_date is when the trade happened; disclosure_date is when it was
# filed. The gap between them is the real lag, which we measure rather than
# assume.
DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d")


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def load_universe(path: Path) -> list[str]:
    with path.open() as fh:
        return [row["ticker"].strip().upper() for row in csv.DictReader(fh)]


def fetch(name: str, url: str) -> list[dict]:
    """Return the feed's transactions, or [] with the failure printed."""
    try:
        resp = requests.get(url, timeout=120)
    except Exception as exc:  # noqa: BLE001 -- reporting the failure IS the result
        print(f"  {name:<7} UNREACHABLE: {type(exc).__name__}: {exc}")
        return []
    if resp.status_code != 200:
        print(f"  {name:<7} HTTP {resp.status_code} ({len(resp.content)} bytes)")
        return []
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        print(f"  {name:<7} HTTP 200 but unparseable JSON: {exc}")
        print(f"          first 200 bytes: {resp.content[:200]!r}")
        return []
    if not isinstance(data, list):
        print(f"  {name:<7} HTTP 200, JSON is {type(data).__name__}, expected list")
        return []
    print(f"  {name:<7} OK — {len(data):,} transactions ({len(resp.content)/1e6:.1f} MB)")
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback-days", type=int, default=365)
    ap.add_argument("--universe", default=str(REPO / "config" / "universe.csv"))
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    universe = load_universe(Path(args.universe))
    wanted = set(universe)
    cutoff = date.today() - timedelta(days=args.lookback_days)

    print("=" * 72)
    print(f"[1] FEED REACHABILITY  (universe: {len(universe)} tickers, "
          f"window: {cutoff} -> {date.today()})")
    print("=" * 72)

    rows: list[tuple[str, dict]] = []
    for name, url in FEEDS.items():
        for tx in fetch(name, url):
            rows.append((name, tx))

    if not rows:
        print("\nVERDICT: both feeds are dead. Congressional trading data is not")
        print("available from this source at any coverage level. The removal")
        print("stands on availability, and re-adding the signal would require")
        print("finding a maintained replacement source first.")
        return 0

    # ---- [2] freshness ---------------------------------------------------
    print()
    print("=" * 72)
    print("[2] FRESHNESS — is the dataset still being updated?")
    print("=" * 72)
    per_feed_latest: dict[str, list[date]] = defaultdict(list)
    lags: list[int] = []
    for feed, tx in rows:
        td = parse_date(tx.get("transaction_date"))
        dd = parse_date(tx.get("disclosure_date"))
        if td:
            per_feed_latest[feed].append(td)
        if td and dd and dd >= td:
            lags.append((dd - td).days)
    for feed in FEEDS:
        dates = per_feed_latest.get(feed, [])
        if not dates:
            print(f"  {feed:<7} no parseable transaction dates")
            continue
        dates.sort()
        stale = (date.today() - dates[-1]).days
        print(f"  {feed:<7} earliest {dates[0]}  latest {dates[-1]}  "
              f"({stale} days stale)")
    if lags:
        lags.sort()
        mid = lags[len(lags) // 2]
        p90 = lags[int(len(lags) * 0.9)]
        print(f"  disclosure lag (transaction -> filing): median {mid}d, p90 {p90}d, "
              f"n={len(lags):,}")

    # ---- [3] in-window coverage -----------------------------------------
    print()
    print("=" * 72)
    print(f"[3] COVERAGE — how many of the {len(universe)} universe tickers appear?")
    print("=" * 72)

    matched: dict[str, Counter] = defaultdict(Counter)
    all_tickers_in_window: Counter = Counter()
    in_window = 0
    for _feed, tx in rows:
        td = parse_date(tx.get("transaction_date"))
        if td is None or td < cutoff:
            continue
        in_window += 1
        ticker = (tx.get("ticker") or "").strip().upper()
        if not ticker or ticker in {"--", "N/A", "NONE"}:
            continue
        all_tickers_in_window[ticker] += 1
        if ticker in wanted:
            kind = (tx.get("type") or "").lower()
            if "purchase" in kind:
                matched[ticker]["buys"] += 1
            elif "sale" in kind:
                matched[ticker]["sells"] += 1
            else:
                matched[ticker]["other"] += 1

    total_buys = sum(c["buys"] for c in matched.values())
    total_sells = sum(c["sells"] for c in matched.values())
    total_other = sum(c["other"] for c in matched.values())
    total_matched = total_buys + total_sells + total_other

    print(f"  in-window congressional transactions (all tickers): {in_window:,}")
    print(f"  distinct tickers traded (all): {len(all_tickers_in_window):,}")
    print()
    print(f"  universe tickers appearing at all: "
          f"{len(matched)} / {len(universe)} "
          f"({100*len(matched)/len(universe):.0f}%)")
    print(f"  transactions landing in universe: {total_matched:,} "
          f"({100*total_matched/in_window:.2f}% of all in-window)")
    print(f"    buys {total_buys:,} | sells {total_sells:,} | unclassified {total_other:,}")
    buyers = [t for t, c in matched.items() if c["buys"] > 0]
    print(f"  universe tickers with at least one BUY: {len(buyers)} / {len(universe)}")

    # ---- [4] which names -------------------------------------------------
    print()
    print("=" * 72)
    print(f"[4] MATCHED NAMES (top {args.top} by transaction count)")
    print("=" * 72)
    if not matched:
        print("  none")
    else:
        ranked = sorted(
            matched.items(),
            key=lambda kv: -(kv[1]["buys"] + kv[1]["sells"] + kv[1]["other"]),
        )
        print(f"  {'ticker':<8}{'buys':>6}{'sells':>7}{'other':>7}")
        for ticker, c in ranked[: args.top]:
            print(f"  {ticker:<8}{c['buys']:>6}{c['sells']:>7}{c['other']:>7}")

    # ---- [5] what Congress actually trades -------------------------------
    print()
    print("=" * 72)
    print("[5] CONTEXT — what Congress actually trades in this window")
    print("=" * 72)
    print(f"  {'ticker':>8}{'txns':>7}   in universe?")
    for ticker, n in all_tickers_in_window.most_common(args.top):
        print(f"  {ticker:>8}{n:>7}   {'YES' if ticker in wanted else '-'}")

    # ---- [6] verdict -----------------------------------------------------
    print()
    print("=" * 72)
    print("[6] READ THIS AS")
    print("=" * 72)
    n = len(buyers)
    print(f"  {n} of {len(universe)} universe names had a congressional BUY in "
          f"{args.lookback_days} days.")
    print("  Under ~10: the column is near-constant in any single weekly window;")
    print("    the degenerate guard would drop it. Removal was justified.")
    print("  Over ~25: enough cross-section to rank on. The removal was wrong on")
    print("    the merits and the signal deserves a walk-forward backtest.")
    print("  In between: marginal — worth a backtest only if buys cluster rather")
    print("    than scattering one-per-name.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
