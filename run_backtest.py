#!/usr/bin/env python3
"""Walk-forward backtest CLI.

Examples:
    python run_backtest.py --start 2024-07-01 --end 2026-07-01
    python run_backtest.py --start 2025-01-01 --step-weeks 2 --top-n 15 \
        --include-filing-text --no-adaptive
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from stock_selector.backtest import (
    BENCHMARKS,
    collect_edgar_histories,
    render_markdown,
    run_backtest,
)
from stock_selector.config import DEFAULT_UNIVERSE_PATH, load_config
from stock_selector.data_sources.edgar import EdgarClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walk-forward signal backtest")
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument(
        "--start", type=date.fromisoformat, default=date.today() - timedelta(days=730)
    )
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--step-weeks", type=int, default=4)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument(
        "--include-filing-text", action="store_true",
        help="Also score 10-Q/10-K language similarity (many document fetches)",
    )
    parser.add_argument(
        "--no-adaptive", action="store_true",
        help="Keep base weights fixed instead of walk-forward IC tilting",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    import yfinance as yf

    config = load_config(universe_path=args.universe)
    universe = config.universe

    fetch_start = (args.start - timedelta(days=400)).isoformat()  # SMA200 warmup
    prices = yf.download(
        tickers=universe, start=fetch_start, interval="1d",
        group_by="column", auto_adjust=True, threads=True, progress=False,
    )
    bench = yf.download(
        tickers=BENCHMARKS, start=args.start.isoformat(), interval="1d",
        auto_adjust=True, progress=False,
    )["Close"]

    client = None
    histories = {"form4": {t: None for t in universe}, "filings": {t: None for t in universe}, "text_cache": None}
    if config.sec_edgar_user_agent:
        client = EdgarClient(config.sec_edgar_user_agent)
        histories = collect_edgar_histories(
            client, universe, args.start - timedelta(days=180),
            include_filing_text=args.include_filing_text,
        )
    else:
        print("WARNING: SEC_EDGAR_USER_AGENT not set — technical-only backtest")

    result = run_backtest(
        universe=universe,
        prices=prices,
        bench_closes=bench,
        histories=histories,
        start=args.start,
        end=args.end,
        step_weeks=args.step_weeks,
        top_n=args.top_n,
        adaptive_weights=not args.no_adaptive,
        include_filing_text=args.include_filing_text,
        client=client,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    md_path = args.output_dir / f"backtest_{args.start}_{args.end}.md"
    md_path.write_text(render_markdown(result, args.top_n, args.step_weeks))
    result.periods.to_csv(args.output_dir / "backtest_periods.csv", index=False)
    result.picks.to_csv(args.output_dir / "backtest_picks.csv", index=False)
    if not result.ic_history.empty:
        result.ic_history.to_csv(args.output_dir / "backtest_ic.csv")
    print(f"Backtest report: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
