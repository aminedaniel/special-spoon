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
    collect_earnings_histories,
    collect_edgar_histories,
    form4_cap_for_window,
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
    parser.add_argument(
        "--skip-edgar", action="store_true",
        help="Score only the price/earnings signals (technical, stability, "
             "earnings_drift). Drops EDGAR entirely, which is what makes a "
             "wide-universe run take ~20 minutes instead of ~10 hours.",
    )
    parser.add_argument(
        "--max-form4", type=int, default=None,
        help="Form 4s fetched per ticker (default: scaled to the window). "
             "Too low and early rebalances see no insider activity at all.",
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
    # Benchmarks from fetch_start too: the stability signal needs a trailing
    # year of QQQ *before* the first rebalance to estimate betas there.
    bench = yf.download(
        tickers=BENCHMARKS, start=fetch_start, interval="1d",
        auto_adjust=True, progress=False,
    )["Close"]

    client = None
    histories = {"form4": {t: None for t in universe}, "filings": {t: None for t in universe}, "text_cache": None}
    if args.skip_edgar:
        print(
            "--skip-edgar: insider/events/filing-text not scored "
            "(technical/stability/earnings-drift only)"
        )
    elif config.sec_edgar_user_agent:
        client = EdgarClient(config.sec_edgar_user_agent)
        edgar_since = args.start - timedelta(days=180)
        cap = args.max_form4 or form4_cap_for_window(edgar_since, args.end)
        client_histories_note = (
            f"Form 4 cap {cap}/ticker over {(args.end - edgar_since).days} days"
        )
        print(f"EDGAR: {client_histories_note}")
        histories = collect_edgar_histories(
            client, universe, edgar_since,
            include_filing_text=args.include_filing_text,
            max_form4=cap,
        )
    else:
        print(
            "WARNING: SEC_EDGAR_USER_AGENT not set — insider/events/filing-text "
            "will not be scored (technical/stability/earnings-drift still run)"
        )
    # Attach after the EDGAR branch: that call builds a fresh dict and would
    # otherwise silently drop the earnings histories.
    histories["earnings"] = collect_earnings_histories(universe)

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
    # Stamp dates AND the parameters that change the result, so variant runs
    # over the same date range (different top-n or rebalance cadence) don't
    # clobber each other.
    # Universe in the stem too: the size experiment runs the same dates and
    # cadence over three different ticker lists.
    uni = args.universe.stem.replace("universe", "").strip("_") or "smid"
    suffix = "_priceonly" if args.skip_edgar else ""
    stem = (
        f"backtest_{uni}_{args.start}_{args.end}"
        f"_top{args.top_n}_{args.step_weeks}w{suffix}"
    )
    md_path = args.output_dir / f"{stem}.md"
    md_path.write_text(render_markdown(result, args.top_n, args.step_weeks))
    result.periods.to_csv(args.output_dir / f"{stem}_periods.csv", index=False)
    result.picks.to_csv(args.output_dir / f"{stem}_picks.csv", index=False)
    if not result.ic_history.empty:
        result.ic_history.to_csv(args.output_dir / f"{stem}_ic.csv")
    print(f"Backtest report: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
