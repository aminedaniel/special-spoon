#!/usr/bin/env python3
"""Rebuild config/universe.csv: small/mid-cap ($300M-$10B) US tech tickers.

Run occasionally (quarterly is plenty) — the weekly pipeline reads the
checked-in CSV and never depends on this script, so listing-source hiccups
can't break the weekly report.

Sources: Nasdaq Trader symbol directory files (free, no key), filtered by
market cap and sector via yfinance.

Usage: python scripts/refresh_universe.py [--limit 400] [--output config/universe.csv]
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import sys
import time
from pathlib import Path

import requests
import yfinance as yf

log = logging.getLogger("refresh_universe")

NASDAQ_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

MIN_CAP = 300e6
MAX_CAP = 10e9
TECH_SECTORS = {"Technology", "Communication Services"}
PAUSE_EVERY = 25
PAUSE_SECS = 1.0


def fetch_symbols() -> list[str]:
    """All common-stock symbols from the Nasdaq Trader directory files."""
    symbols: list[str] = []
    for url, sym_col in ((NASDAQ_LISTED, "Symbol"), (OTHER_LISTED, "ACT Symbol")):
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text), delimiter="|")
        for row in reader:
            sym = (row.get(sym_col) or "").strip()
            if not sym or not sym.isalpha():
                continue  # skip units/warrants/preferreds with . or $ suffixes
            if (row.get("ETF") or "").strip() == "Y":
                continue
            if (row.get("Test Issue") or "").strip() == "Y":
                continue
            symbols.append(sym)
    return sorted(set(symbols))


def filter_tech_smid(symbols: list[str], limit: int | None) -> list[dict]:
    """Keep symbols in the cap band + tech sectors, via yfinance lookups."""
    keep: list[dict] = []
    for i, sym in enumerate(symbols):
        try:
            info = yf.Ticker(sym).info
        except Exception:  # noqa: BLE001 — skip and move on
            continue
        cap = info.get("marketCap")
        sector = info.get("sector")
        if cap and sector in TECH_SECTORS and MIN_CAP <= cap <= MAX_CAP:
            keep.append({"ticker": sym, "name": info.get("shortName", ""), "sector": sector})
            log.info("kept %s (%s, $%.1fB)", sym, sector, cap / 1e9)
            if limit and len(keep) >= limit:
                break
        if (i + 1) % PAUSE_EVERY == 0:
            time.sleep(PAUSE_SECS)
    return keep


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("config/universe.csv"))
    parser.add_argument(
        "--limit", type=int, default=400,
        help="Stop after this many matches (keeps runtime bounded)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    symbols = fetch_symbols()
    log.info("%d listed symbols to screen", len(symbols))
    rows = filter_tech_smid(symbols, args.limit)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ticker", "name", "sector"])
        writer.writeheader()
        writer.writerows(rows)
    log.info("wrote %d tickers to %s", len(rows), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
