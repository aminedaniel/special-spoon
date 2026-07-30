"""Earnings surprises from yfinance, for post-earnings-announcement drift.

PEAD is the oldest documented anomaly still alive (Ball & Brown 1968;
Bernard & Thomas 1989): stocks that beat expectations keep drifting up for
~60 trading days after the announcement, because the market underreacts to
the news. Retail chases the announcement-day pop and misses the drift.

`Ticker.get_earnings_dates` returns past and scheduled announcements with
EPS estimate, reported EPS, and surprise. Only *past* announcements with a
reported number carry information; the drift decays, so an announcement
older than DRIFT_WINDOW_DAYS contributes nothing (NaN, weight redistributes).
"""

from __future__ import annotations

import logging
import time
from datetime import date

import numpy as np
import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

# Drift is strongest over the first ~60 trading days (~85 calendar); scoring
# past that would rank stale news. 75 calendar days keeps most of the effect
# while covering a normal quarterly cycle with slack for late reporters.
DRIFT_WINDOW_DAYS = 75
MIN_PRIOR_SURPRISES = 4   # below this, fall back to the raw surprise pct
MAX_QUARTERS = 12
# The backtest needs enough quarters to cover its whole window plus the
# prior-surprise baseline used by the SUE scaling.
BACKTEST_QUARTERS = 24
BATCH_PAUSE_EVERY = 25
BATCH_PAUSE_SECS = 1.0


def standardized_surprise(
    surprises_pct: list[float], latest_pct: float
) -> float:
    """SUE-style score: latest surprise scaled by the volatility of the
    ticker's own past surprises.

    A +5% beat means much more from a company that usually lands within 1%
    of estimates than from one that routinely swings ±20%. With too few
    priors (or degenerate zero spread) the raw surprise is used unscaled.
    """
    priors = [s for s in surprises_pct if not np.isnan(s)]
    if len(priors) < MIN_PRIOR_SURPRISES:
        return latest_pct
    spread = float(np.std(priors, ddof=1))
    if spread <= 1e-9:
        return latest_pct
    return latest_pct / spread


def fetch_earnings_surprise(
    tickers: list[str], as_of: date | None = None
) -> dict[str, dict | None]:
    """Per-ticker latest in-window earnings surprise.

    Returns {ticker: {"sue": float, "surprise_pct": float, "days_since": int}
    or None} — None means no scorable announcement (nothing reported inside
    the drift window, or no estimates), which the signal treats as 'no
    information', not zero.
    """
    as_of = as_of or date.today()
    out: dict[str, dict | None] = {}
    for i, ticker in enumerate(tickers):
        out[ticker] = None
        try:
            frame = yf.Ticker(ticker).get_earnings_dates(limit=MAX_QUARTERS)
            if frame is None or frame.empty:
                continue
            parsed = surprise_asof(frame, as_of)
        except Exception as exc:  # noqa: BLE001 — per-ticker failures are non-fatal
            log.warning("earnings surprise failed for %s: %s", ticker, exc)
            continue
        if parsed is not None:
            out[ticker] = parsed
        if (i + 1) % BATCH_PAUSE_EVERY == 0:
            time.sleep(BATCH_PAUSE_SECS)
    scored = sum(1 for v in out.values() if v is not None)
    log.info("earnings surprises: %d/%d tickers in drift window", scored, len(out))
    return out


def fetch_earnings_history(
    tickers: list[str], limit: int = BACKTEST_QUARTERS
) -> dict[str, pd.DataFrame | None]:
    """Raw dated earnings frames per ticker, fetched once for the backtest.

    Every row is a dated announcement with its estimate and reported EPS, so
    `surprise_asof` can reconstruct the signal at any past rebalance without
    lookahead — the same code path the weekly run uses for 'today'.
    """
    out: dict[str, pd.DataFrame | None] = {}
    for i, ticker in enumerate(tickers):
        out[ticker] = None
        try:
            frame = yf.Ticker(ticker).get_earnings_dates(limit=limit)
            if frame is not None and not frame.empty:
                out[ticker] = frame
        except Exception as exc:  # noqa: BLE001 — per-ticker failures are non-fatal
            log.debug("earnings history failed for %s: %s", ticker, exc)
        if (i + 1) % BATCH_PAUSE_EVERY == 0:
            time.sleep(BATCH_PAUSE_SECS)
    return out


def surprise_asof(frame: pd.DataFrame, as_of: date) -> dict | None:
    """Extract the newest reported announcement within the drift window.

    Defensive about what yfinance actually returns per ticker: the index may
    be tz-aware or tz-naive, and some issuers come back with duplicate
    announcement timestamps (restatements, dual rows). A duplicate makes
    `.loc[ts]` return a Series instead of a scalar, which would blow up the
    arithmetic below — so duplicates are collapsed to the last row first.
    """
    f = frame.copy()
    idx = pd.to_datetime(f.index, errors="coerce", utc=True)
    f.index = idx.tz_localize(None) if idx.tz is not None else idx
    f = f[f.index.notna()]
    if f.empty:
        return None
    f = f[~f.index.duplicated(keep="last")].sort_index()

    reported = pd.to_numeric(f.get("Reported EPS"), errors="coerce")
    estimate = pd.to_numeric(f.get("EPS Estimate"), errors="coerce")
    if reported is None or estimate is None:
        return None

    past = f.index.date <= as_of
    has_both = reported.notna().values & estimate.notna().values
    usable = f.index[past & has_both]
    if len(usable) == 0:
        return None

    latest_ts = usable[-1]
    days_since = (as_of - latest_ts.date()).days
    if days_since > DRIFT_WINDOW_DAYS:
        return None

    est = float(estimate.loc[latest_ts])
    act = float(reported.loc[latest_ts])

    # Surprise relative to |estimate|; a near-zero estimate would explode the
    # ratio, so floor the denominator (interpretation: cents of beat).
    denom = max(abs(est), 0.01)
    latest_pct = (act - est) / denom * 100.0

    prior_mask = (f.index < latest_ts) & pd.Series(has_both, index=f.index)
    priors = [
        float((reported.loc[ts] - estimate.loc[ts]) / max(abs(estimate.loc[ts]), 0.01) * 100.0)
        for ts in f.index[prior_mask]
    ]
    return {
        "sue": standardized_surprise(priors, latest_pct),
        "surprise_pct": latest_pct,
        "days_since": days_since,
    }
