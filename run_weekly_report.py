#!/usr/bin/env python3
"""CLI entrypoint for the weekly stock selector.

Examples:
    python run_weekly_report.py
    python run_weekly_report.py --universe my_watchlist.csv --top-n 10
    python run_weekly_report.py --dry-run   # Stage A only, no EDGAR/congress/FRED
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from stock_selector.config import (
    DEFAULT_UNIVERSE_PATH,
    DEFAULT_WEIGHTS_PATH,
    load_config,
)
from stock_selector.pipeline import run
from stock_selector.report import write_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Weekly stock selector")
    parser.add_argument(
        "--universe", type=Path, default=DEFAULT_UNIVERSE_PATH,
        help="CSV with a 'ticker' column (default: config/universe.csv)",
    )
    parser.add_argument(
        "--weights", type=Path, default=DEFAULT_WEIGHTS_PATH,
        help="weights.yaml path (default: config/weights.yaml)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("output"),
        help="Directory for report files (default: output/)",
    )
    parser.add_argument(
        "--top-n", type=int, default=None,
        help="Override report.top_n from weights.yaml",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Stage A only: skip insider/congress/FRED calls",
    )
    parser.add_argument(
        "--no-adaptive", action="store_true",
        help="Ignore reports/adaptive_weights.yaml and use base weights",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    weights_path = args.weights
    adaptive_path = Path("reports/adaptive_weights.yaml")
    if (
        weights_path == DEFAULT_WEIGHTS_PATH
        and not args.no_adaptive
        and adaptive_path.exists()
    ):
        weights_path = adaptive_path
        logging.getLogger(__name__).info(
            "using IC-adapted weights from %s", adaptive_path
        )

    config = load_config(weights_path=weights_path, universe_path=args.universe)
    top_n = args.top_n or config.top_n

    result = run(config, skip_stage_b=args.dry_run)
    md_path, csv_path = write_report(result, top_n, args.output_dir)

    print(f"Report:   {md_path}")
    print(f"Rankings: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
