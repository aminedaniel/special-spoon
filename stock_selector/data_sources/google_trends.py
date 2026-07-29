"""Google Trends search-interest momentum via pytrends (free, no auth).

Design note — why momentum, not raw interest:
Google Trends normalizes every request to its own peak (max=100 within the
request's keywords AND timeframe), so the raw 0-100 values are NOT comparable
across separate requests/tickers. Instead we reduce each ticker's series to a
*recent-vs-baseline ratio* (how elevated is search interest now versus its own
trailing average). That ratio is scale-invariant — the per-request 100
normalization cancels — so it IS comparable cross-sectionally after ranking.

The signal measures retail *attention*, not direction. Whether rising attention
is bullish or bearish is unproven, so it carries a small weight and the
scoreboard/backtest IC tracking decides its real sign and value over time.

Rate limits: Google Trends is aggressively throttled. Requests are batched 5
keywords at a time (the API maximum) with pauses, and any failure fails soft —
a ticker with no data contributes nothing and its weight redistributes.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import date, timedelta

import pandas as pd

log = logging.getLogger(__name__)

BATCH_SIZE = 5          # Google Trends allows up to 5 keywords per request
BATCH_PAUSE_SECS = 8.0  # inter-batch pause; Google Trends throttles aggressively
RECENT_DAYS = 14        # "now" window
BASELINE_DAYS = 90      # trailing window the recent period is compared against
SEARCH_SUFFIX = "stock"  # disambiguates tickers like S / U / DBX toward the equity

MAX_BATCH_RETRIES = 3          # per-batch attempts before giving up on that batch
RETRY_BACKOFF_BASE_SECS = 8.0   # exponential: 8s, 16s between retries
INITIAL_JITTER_MAX_SECS = 3.0   # random start delay to avoid a synchronized burst
MAX_TOTAL_SECONDS = 120.0       # hard wall-clock budget for the whole signal; from
                                # CI IPs Google throttles heavily, and without a cap
                                # the retries could stall a run for many minutes.


def interest_momentum(
    series: pd.Series, recent_days: int = RECENT_DAYS
) -> float | None:
    """Recent-mean / baseline-mean - 1 for one ticker's interest-over-time.

    `baseline` is the window excluding the most recent `recent_days`, so the
    comparison is recent vs prior. Returns None when there isn't enough data or
    the baseline is empty/zero (no historical interest → ratio undefined).
    """
    s = series.dropna()
    if len(s) < recent_days + 5:
        return None
    recent = s.iloc[-recent_days:]
    baseline = s.iloc[:-recent_days]
    if baseline.empty:
        return None
    baseline_mean = float(baseline.mean())
    if baseline_mean <= 0:
        return None
    return float(recent.mean()) / baseline_mean - 1.0


def _timeframe(as_of: date | None, baseline_days: int) -> str:
    """pytrends timeframe string. Live uses a rolling window; a supplied
    as_of builds an explicit range so the signal is reconstructable for
    backtests (no lookahead)."""
    if as_of is None:
        return "today 3-m"
    start = as_of - timedelta(days=baseline_days + 7)
    return f"{start.isoformat()} {as_of.isoformat()}"


def _fetch_batch(pytrends, batch: list[str], timeframe: str, deadline: float):
    """One batch with exponential backoff on throttling. Returns the
    interest-over-time DataFrame, or None if every attempt failed or the
    overall time budget (`deadline`, a monotonic timestamp) is exhausted."""
    for attempt in range(MAX_BATCH_RETRIES):
        try:
            pytrends.build_payload(batch, timeframe=timeframe)
            return pytrends.interest_over_time()
        except Exception as exc:  # noqa: BLE001 — throttling/errors are non-fatal
            wait = RETRY_BACKOFF_BASE_SECS * (2 ** attempt) + random.uniform(0, 3)
            if attempt == MAX_BATCH_RETRIES - 1 or time.monotonic() + wait > deadline:
                log.warning(
                    "Google Trends batch gave up (%s...): %s", batch[0], exc
                )
                return None
            log.info(
                "Google Trends batch throttled (%s...), retry %d/%d in %.0fs: %s",
                batch[0], attempt + 1, MAX_BATCH_RETRIES - 1, wait, exc,
            )
            time.sleep(wait)
    return None


def fetch_interest_momentum(
    tickers: list[str],
    as_of: date | None = None,
    recent_days: int = RECENT_DAYS,
    baseline_days: int = BASELINE_DAYS,
) -> dict[str, float | None]:
    """Search-interest momentum per ticker. Fails soft per batch, with
    exponential backoff so transient Google Trends throttling doesn't wipe
    out the whole signal."""
    from pytrends.request import TrendReq

    out: dict[str, float | None] = {t: None for t in tickers}
    try:
        # urllib3-level retries/backoff on the underlying HTTP session, on top
        # of the per-batch retry loop below (pytrends raises its own error on
        # a 429, which the outer loop catches).
        pytrends = TrendReq(
            hl="en-US", tz=0, timeout=(10, 30), retries=2, backoff_factor=1.0
        )
    except Exception as exc:  # noqa: BLE001 — no client, no signal
        log.warning("pytrends init failed: %s", exc)
        return out

    timeframe = _timeframe(as_of, baseline_days)
    keyword_for = {f"{t} {SEARCH_SUFFIX}": t for t in tickers}
    keywords = list(keyword_for)

    deadline = time.monotonic() + MAX_TOTAL_SECONDS
    time.sleep(random.uniform(0, INITIAL_JITTER_MAX_SECS))
    for i in range(0, len(keywords), BATCH_SIZE):
        if time.monotonic() > deadline:
            log.warning(
                "Google Trends time budget (%.0fs) exhausted; %d tickers left unpriced",
                MAX_TOTAL_SECONDS,
                len(keywords) - i,
            )
            break
        batch = keywords[i : i + BATCH_SIZE]
        df = _fetch_batch(pytrends, batch, timeframe, deadline)
        if df is None or df.empty:
            time.sleep(BATCH_PAUSE_SECS)
            continue
        # Drop the still-open final bucket: pytrends flags it isPartial, and an
        # incomplete current-period value would otherwise land in the "recent"
        # window and be scored as a complete observation.
        if "isPartial" in df.columns:
            df = df[~df["isPartial"].astype(bool)]
        for kw in batch:
            if kw in df.columns:
                out[keyword_for[kw]] = interest_momentum(df[kw], recent_days)
        time.sleep(BATCH_PAUSE_SECS)
    return out
