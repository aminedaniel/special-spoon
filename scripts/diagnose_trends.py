#!/usr/bin/env python3
"""Find out what Google Trends actually returns to this runner.

The weekly report has said "Google Trends signal unavailable (likely
rate-limited)" in 7 of 8 reports, and the signal has never once written a
score. "Likely rate-limited" was a guess baked into the message, never a
diagnosis — the retry/backoff machinery in the signal was built for
transient throttling without confirming that is the failure mode.

This prints the raw outcome: pytrends version, the exact exception type and
message, and the HTTP status Google returns. A 429 means blocked/throttled
(and from a datacenter IP that is categorical, not transient). A 200 with an
empty frame means something else entirely and the signal is fixable.

Run in CI, where the failure actually happens: python scripts/diagnose_trends.py
"""

from __future__ import annotations

import sys
import traceback


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("pytrends")
    except Exception as exc:  # noqa: BLE001
        return f"unknown ({exc})"


def _describe(exc: BaseException) -> None:
    """Print everything useful hanging off an exception, including any HTTP
    response pytrends/requests attached to it."""
    print(f"   type:    {type(exc).__module__}.{type(exc).__name__}")
    print(f"   message: {exc}")
    resp = getattr(exc, "response", None)
    if resp is not None:
        print(f"   HTTP status: {getattr(resp, 'status_code', '?')}")
        body = (getattr(resp, "text", "") or "")[:300].replace("\n", " ")
        print(f"   body[:300]:  {body!r}")
    for attr in ("status_code", "code", "errno"):
        if hasattr(exc, attr):
            print(f"   {attr}: {getattr(exc, attr)}")


def main() -> int:
    print(f"pytrends version: {_version()}")
    print(f"python: {sys.version.split()[0]}\n")

    # 1. Does the client even construct? (No network on older versions.)
    print("[1] TrendReq(...) construction")
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 30))
        print("   OK\n")
    except Exception as exc:  # noqa: BLE001
        print("   FAILED")
        _describe(exc)
        traceback.print_exc()
        return 0  # diagnostic: report, never fail the job

    # 2. The exact call the signal makes, on one well-known keyword.
    for label, kwargs in [
        ("single keyword, 3-month rolling", {"kw_list": ["AAPL stock"], "timeframe": "today 3-m"}),
        ("single bare keyword, 12-month", {"kw_list": ["Apple"], "timeframe": "today 12-m"}),
        ("batch of 5, as the signal sends", {
            "kw_list": ["RNG stock", "CARG stock", "DBX stock", "YELP stock", "TENB stock"],
            "timeframe": "today 3-m",
        }),
    ]:
        print(f"[2] build_payload + interest_over_time — {label}")
        try:
            pytrends.build_payload(**kwargs)
            df = pytrends.interest_over_time()
            if df is None:
                print("   returned None\n")
            elif df.empty:
                print("   HTTP OK but EMPTY frame — not a block; signal logic issue\n")
            else:
                print(f"   SUCCESS: {df.shape[0]} rows x {df.shape[1]} cols")
                print(f"   columns: {list(df.columns)}")
                print(f"   tail:\n{df.tail(3)}\n")
        except Exception as exc:  # noqa: BLE001
            print("   FAILED")
            _describe(exc)
            print()

    print("=== VERDICT ===")
    print("429 / TooManyRequests  -> Google is blocking this runner. Datacenter")
    print("                          IPs are blocked categorically; backoff cannot")
    print("                          fix it. Drop the signal or move it off CI.")
    print("empty frame, HTTP 200  -> not blocked; the signal's parsing is at fault.")
    print("success                -> the failure is intermittent after all.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
