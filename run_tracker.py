#!/usr/bin/env python3
"""Update the recommendation tracker from the latest report's rankings.

Adds this run's top-N picks (default 2) to a running ledger, anchored to the
first date each was recommended, and refreshes current prices.

Usage:
    python run_tracker.py --reports-dir reports            # uses newest rankings
    python run_tracker.py --rankings reports/rankings_2026-07-28.csv --top-n 2
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from stock_selector.tracker import update_tracker

RANKINGS_GLOB = "rankings_*.csv"


def _newest_rankings(reports_dir: Path) -> Path | None:
    files = sorted(reports_dir.glob(RANKINGS_GLOB))
    return files[-1] if files else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update the recommendation tracker")
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument(
        "--rankings", type=Path, default=None,
        help="Rankings CSV to read top picks from (default: newest in reports-dir)",
    )
    parser.add_argument("--top-n", type=int, default=2)
    parser.add_argument(
        "--backfill", action="store_true",
        help="Seed the ledger from all past rankings_*.csv using historical closes",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    rankings = args.rankings or _newest_rankings(args.reports_dir)
    if rankings is None and not args.backfill:
        print(f"No rankings CSV found in {args.reports_dir}; nothing to track.")
        return 0

    md_path = update_tracker(
        rankings, args.reports_dir, top_n=args.top_n, backfill=args.backfill
    )
    print(f"Tracker: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
