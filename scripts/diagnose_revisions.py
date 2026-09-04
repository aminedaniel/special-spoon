#!/usr/bin/env python3
"""Can analyst estimate revisions be measured honestly on this universe?

The literature says revisions predict returns — Chan/Jegadeesh/Lakonishok
(1996) is the foundational result, post-forecast revision drift is a documented
underreaction effect, and the effect concentrates in firms with LOW ANALYST
COVERAGE, which is exactly this universe. That is why it is worth testing.

It is not worth assuming. Two things have to be true before a signal is built,
and both are empirical questions this script answers rather than argues:

  POINT-IN-TIME. A backtest needs consensus AS IT STOOD on a past date. If the
  endpoint returns today's consensus attached to past fiscal periods, every
  historical score is lookahead and there is no honest test to run. This is the
  same uncertainty still open on share counts; it gets settled here first.

  COVERAGE. $300M-$20B tech names carry perhaps 3-8 analysts, and some carry
  none. If fewer than ~40 of 99 tickers have usable dated history the column is
  near-constant, the degenerate guard drops it, and the weight is wasted —
  which is precisely what happened to events and to insider buying.

The script probes each endpoint and DUMPS THE RAW FIELD STRUCTURE rather than
assuming a schema. Guessing schemas is what produced the Trends failure, the
Form 4 XSL bug, the events window and the filing-pair bug.

Writes nothing. Never logs the API key.

    FINNHUB_API_KEY=... python scripts/diagnose_revisions.py --limit 99
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests

BASE = "https://finnhub.io/api/v1"
# Probed, not assumed: the free tier does not serve everything, and which of
# these answers decides what a signal could even be built from.
ENDPOINTS = {
    "eps-estimate": "/stock/eps-estimate",
    "revenue-estimate": "/stock/revenue-estimate",
    "recommendation": "/stock/recommendation",
    "upgrade-downgrade": "/stock/upgrade-downgrade",
    "earnings-surprise": "/stock/earnings",
}
# Anything that looks like it records WHEN an estimate was made, as opposed to
# which fiscal period it is about. The distinction is the whole question.
DATE_HINTS = ("date", "period", "time", "updated", "gradetime", "lastupdated")
RATE_PAUSE = 1.1          # free tier is ~60 calls/min; stay well under

# A backtest over 2022-07 -> now needs roughly 50 monthly observations. Four
# distinct dates is not a history, and the first version of this script passed
# a ticker on exactly that because its threshold happened to equal the record
# count the API returns. Depth is now checked in days, not in row count.
MIN_HISTORY_DAYS = 730
# Quarter ends mean the field names the fiscal period an estimate is ABOUT.
# Only a capture date supports point-in-time scoring, and the two look
# identical to a field-name match — which is how the first run mislabelled
# earnings-surprise as a dated series.
QUARTER_ENDS = {(3, 31), (6, 30), (9, 30), (12, 31)}


def get(path: str, key: str, **params) -> tuple[int, object]:
    params["token"] = key
    try:
        r = requests.get(f"{BASE}{path}", params=params, timeout=30)
    except Exception as exc:  # noqa: BLE001 — reporting the failure IS the result
        return -1, f"{type(exc).__name__}: {exc}"
    try:
        return r.status_code, r.json()
    except Exception:  # noqa: BLE001
        return r.status_code, r.text[:200]


def date_span_days(values: list[str]) -> int:
    """Calendar span covered by a set of date-like strings, 0 if unparseable."""
    parsed = []
    for v in values:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                parsed.append(datetime.strptime(str(v)[:19], fmt).date())
                break
            except ValueError:
                continue
    return (max(parsed) - min(parsed)).days if len(parsed) >= 2 else 0


def looks_like_fiscal_periods(values: list[str]) -> bool:
    """True when the dates sit on calendar quarter ends — i.e. the field names
    the period an estimate covers, not when the estimate was made."""
    hits = tot = 0
    for v in values:
        try:
            d = datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        tot += 1
        hits += (d.month, d.day) in QUARTER_ENDS
    return tot > 0 and hits / tot > 0.5


def shape(payload: object) -> str:
    if isinstance(payload, dict):
        return f"dict keys={sorted(payload)[:8]}"
    if isinstance(payload, list):
        return f"list len={len(payload)}"
    return type(payload).__name__


def records(payload: object) -> list[dict]:
    """Finnhub returns either a bare list or {data: [...]}."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for k in ("data", "earningsCalendar"):
            v = payload.get(k)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers-from", default="config/universe.csv")
    ap.add_argument("--limit", type=int, default=99)
    ap.add_argument("--probe-ticker", default="RNG")
    args = ap.parse_args()

    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        print("FINNHUB_API_KEY not set.")
        print()
        print("Add it as a GitHub Actions secret named FINNHUB_API_KEY")
        print("(Settings -> Secrets and variables -> Actions -> New secret).")
        print("Free tier: https://finnhub.io/register")
        print("Do NOT paste the key into chat or commit it.")
        return 1

    with open(args.tickers_from) as fh:
        tickers = [r["ticker"].strip().upper() for r in csv.DictReader(fh)][: args.limit]

    print("=== analyst-revision feasibility diagnostic ===")
    print(f"{len(tickers)} tickers; probe ticker {args.probe_ticker}\n")

    # ---- [1] which endpoints the free tier actually serves ------------------
    print("[1] ENDPOINT ACCESS (free tier serves a subset — measured, not assumed)")
    available: dict[str, object] = {}
    for name, path in ENDPOINTS.items():
        status, payload = get(path, key, symbol=args.probe_ticker, freq="quarterly")
        n = len(records(payload))
        print(f"  {name:<18} HTTP {status:<4} {shape(payload):<40} records={n}")
        if status == 200 and n:
            available[name] = payload
        time.sleep(RATE_PAUSE)
    if not available:
        print("\n  No endpoint returned usable data. Nothing further can be measured.")
        return 0

    # ---- [2] raw field census ---------------------------------------------
    print("\n[2] FIELD CENSUS — the actual schema, not a guessed one")
    for name, payload in available.items():
        recs = records(payload)
        fields = sorted({k for r in recs for k in r})
        print(f"  {name}: {fields}")
        print(f"      sample: {json.dumps(recs[0], default=str)[:220]}")

    # ---- [3] the decisive question ----------------------------------------
    print("\n[3] POINT-IN-TIME OR RESTATED?")
    print("    A field naming the FISCAL PERIOD an estimate is about is not the")
    print("    same as one naming WHEN the estimate was made. Only the latter")
    print("    supports a backtest.")
    verdict_pit = {}
    for name, payload in available.items():
        recs = records(payload)
        fields = sorted({k for r in recs for k in r})
        hits = [f for f in fields if any(h in f.lower() for h in DATE_HINTS)]
        # A dated SERIES has many distinct values in its date field; a
        # per-period snapshot has one row per fiscal period and no capture time.
        usable = False
        for f in hits:
            vals = [r[f] for r in recs if r.get(f) is not None]
            span = date_span_days([str(v) for v in vals])
            fiscal = looks_like_fiscal_periods([str(v) for v in vals])
            deep = span >= MIN_HISTORY_DAYS
            ok = deep and not fiscal
            usable = usable or ok
            why = (
                "fiscal periods, not capture dates" if fiscal
                else f"only {span}d of history, need {MIN_HISTORY_DAYS}d" if not deep
                else "usable dated series"
            )
            print(f"  {name:<18} {f:<12} n={len(vals):<4} span={span:>5}d  "
                  f"-> {why}")
        verdict_pit[name] = usable

    # ---- [4] coverage across the real universe -----------------------------
    best = next((n for n in ("eps-estimate", "recommendation") if n in available),
                next(iter(available)))
    print(f"\n[4] COVERAGE across {len(tickers)} tickers, using '{best}'")
    covered, empty, errored = [], [], []
    analyst_counts: list[int] = []
    for t in tickers:
        status, payload = get(ENDPOINTS[best], key, symbol=t, freq="quarterly")
        recs = records(payload)
        if status != 200:
            errored.append((t, status))
        elif not recs:
            empty.append(t)
        else:
            covered.append(t)
            for r in recs:
                for k in ("numberAnalysts", "buy", "strongBuy"):
                    if isinstance(r.get(k), (int, float)):
                        analyst_counts.append(int(r[k]))
                        break
        time.sleep(RATE_PAUSE)
    print(f"  with data     {len(covered)}/{len(tickers)}")
    print(f"  empty         {len(empty)}  {empty[:12]}")
    print(f"  http errors   {len(errored)}  {errored[:6]}")
    if analyst_counts:
        analyst_counts.sort()
        mid = analyst_counts[len(analyst_counts) // 2]
        thin = sum(1 for c in analyst_counts if c <= 3)
        print(f"  analysts/record: median {mid}, min {analyst_counts[0]}, "
              f"max {analyst_counts[-1]}, {100*thin/len(analyst_counts):.0f}% "
              f"have <=3")

    # ---- [5] verdict against the pre-committed stop conditions -------------
    print("\n[5] READ THIS AS")
    pit_ok = any(verdict_pit.values())
    cov_ok = len(covered) >= 40
    print(f"  point-in-time data with {MIN_HISTORY_DAYS}d+ depth : "
          f"{'YES' if pit_ok else 'NO'}")
    print(f"  coverage >= 40/99            : {'YES' if cov_ok else 'NO'} "
          f"({len(covered)})")
    if pit_ok and cov_ok:
        print("  -> Both stop conditions cleared. Build the signal and backtest it.")
    elif not pit_ok:
        print("  -> STOP. Only per-period snapshots are available, so a backtest")
        print("     would score the past with today's consensus. That is")
        print("     lookahead, and no weighting could be justified from it.")
    else:
        print("  -> STOP. Coverage is too thin; the column would be")
        print("     near-constant and the degenerate guard would drop it,")
        print("     exactly as happened to events and to insider buying.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
