#!/usr/bin/env python3
"""Update the pick-performance scoreboard from past reports.

Usage: python run_scoreboard.py [--reports-dir reports] [--top-n 20]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from stock_selector.scoreboard import update_scoreboard


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade past weekly reports")
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--top-n", type=int, default=20)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    md_path = update_scoreboard(args.reports_dir, top_n=args.top_n)
    if md_path is None:
        print("No reports old enough to grade yet.")
    else:
        print(f"Scoreboard: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
