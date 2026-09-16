"""Residual momentum: 12-1 momentum measured on returns net of market beta.

Blitz, Huij & Martens (2011) report that momentum computed on the residuals of
a factor model is as strong as raw momentum and markedly less crash-prone,
because raw 12-1 momentum partly rides beta: in a rising market a high-beta
name accumulates "momentum" it did not earn idiosyncratically, and gives it
back violently when the market turns. Residualizing removes that component.

Construction here, and how it differs from the paper:

  * Single factor (QQQ) rather than Fama-French three. There is no factor
    library in this repo and no free point-in-time source for one, so the
    market leg is all that can be removed. Size and value loadings stay in the
    residual. This is an approximation of Blitz et al., not a replication of
    it, and it should not be described as one.
  * The beta is the same cov/var estimate the stability signal uses, taken
    from stability.beta_and_idio_vol so the two signals cannot drift apart in
    what "beta" means.
  * Residuals are cumulated over t-12m -> t-1m (the Jegadeesh-Titman window,
    skipping the reversal month) and divided by their own standard deviation
    over that window, so a quiet stock with a steady residual drift is not
    outranked by a noisy one that happened to end high.

Two things were measured before writing this, because both could have made the
signal meaningless:

  1. The estimation window overlapping the ranking window does NOT degenerate
     it. The worry was that residuals sum to ~zero over their own estimation
     window, which would turn the cumulated figure into minus the excluded
     month — a reversal signal wearing a momentum name. On simulated data with
     a known residual drift, the 1y-estimation variant recovered that drift as
     well as a 2y-estimation variant (rho +0.631 vs +0.629) and was
     uncorrelated with last-month return (rho -0.017). So the live one-year
     price fetch is sufficient and the pipeline did not need changing.

  2. It is highly collinear with raw 12-1 momentum (rho +0.965 in the same
     simulation) and detected the drift no better (+0.631 vs +0.630). What it
     did do is strip the beta loading: rho against beta fell from -0.179 for
     raw momentum to +0.046. So the honest claim is "same information, cleaner
     of market exposure", not "new information". Whether that matters on the
     live universe is what tracking it is for.

Unscored on purpose: it enters with weight 0.0 and reports an IC each week
like any other tracked signal. Nothing here earns weight without measurement.

No benchmark means no residual, so the score is NaN rather than a fallback to
raw momentum — falling back would silently duplicate the technical signal and
report it as a second, agreeing opinion.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import percentile_score
from .stability import beta_and_idio_vol

TRADING_DAYS_1M = 21
TRADING_DAYS_12M = 252
MIN_RANK_DAYS = 126  # at least ~6 months inside the 12-1 window

# Residual vol must be at least this fraction of the stock's own return vol for
# the ratio below to mean anything. A name whose returns are a near-exact
# multiple of the benchmark leaves residuals at floating-point noise (~1e-17),
# and noise divided by noise is not zero — it is an arbitrary number of order
# one. Measured: a series constructed as exactly 1.8x the benchmark produced
# sum 1.68e-16 over std 1.70e-17 = 9.92, which would have ranked at the very
# top of the cross-section on nothing at all. A `sd > 0` check does not catch
# this because the standard deviation is genuinely positive, just meaningless.
MIN_RESIDUAL_VOL_RATIO = 0.01

# The same trap one level up, in the benchmark. stability.beta_and_idio_vol
# rejects a benchmark with `var_b <= 0`, but a flat series does not have
# variance zero — pd.Series([0.0009] * 300).var() is 1.18e-38 — so the guard
# does not fire and the returned beta is meaningless (measured: -1.81 for a
# series built with beta +2.0). QQQ always has real variance, so this is
# latent rather than live in the weekly run, and fixing it inside stability is
# a change to a different signal; guarding relatively here keeps it local.
MIN_BENCH_VOL_RATIO = 0.01


def residual_momentum(
    returns: pd.Series, bench_returns: pd.Series | None
) -> float:
    """Cumulative beta-adjusted return over t-12m -> t-1m, in units of its own
    residual volatility. NaN when there is no usable idiosyncratic component.

    The beta is estimated on the SAME t-12m -> t-1m window that is cumulated,
    with the most recent month dropped first. Blitz et al. estimate over a
    longer trailing window, but excluding the reversal month from the
    estimation too makes the score exactly insensitive to it, rather than
    nearly so: otherwise a large last-month move shifts the beta, which shifts
    every residual in the ranking window, and the month the construction exists
    to ignore leaks back in through the regression. The cost is a beta three
    weeks stale, which is immaterial at this horizon.
    """
    if bench_returns is None:
        return float("nan")

    joined = pd.concat([returns.dropna(), bench_returns], axis=1, join="inner").dropna()
    # Drop the reversal month before anything is estimated, then take the
    # 12-month window that ends there.
    window = joined.iloc[-TRADING_DAYS_12M:-TRADING_DAYS_1M]
    if len(window) < MIN_RANK_DAYS:
        return float("nan")

    r, b = window.iloc[:, 0], window.iloc[:, 1]
    own_vol = float(r.std())
    if not own_vol > 0 or float(b.std()) / own_vol < MIN_BENCH_VOL_RATIO:
        return float("nan")

    beta, _ = beta_and_idio_vol(r, b)
    if np.isnan(beta):
        return float("nan")

    resid = r - beta * b
    sd = float(resid.std())
    if sd / own_vol < MIN_RESIDUAL_VOL_RATIO:
        return float("nan")
    return float(resid.sum() / sd)


def score(
    price_history: pd.DataFrame, bench_close: pd.Series | None = None
) -> pd.Series:
    """Percentile-rank residual momentum cross-sectionally, higher is better."""
    closes = price_history["Close"]
    bench_returns = (
        bench_close.pct_change().dropna() if bench_close is not None else None
    )

    raw = pd.Series(
        {
            ticker: residual_momentum(closes[ticker].pct_change(), bench_returns)
            for ticker in closes.columns
        },
        dtype=float,
    )
    if raw.dropna().empty:
        return pd.Series(np.nan, index=raw.index, dtype=float)
    return percentile_score(raw)
