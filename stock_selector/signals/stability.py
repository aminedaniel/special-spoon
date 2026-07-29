"""Stability signal: low beta + low idiosyncratic volatility, 0-100.

The low-risk anomaly (Ang et al. 2006; Frazzini & Pedersen's betting-
against-beta): high-beta, high-idio-vol names systematically underperform
on a risk-adjusted basis — lottery-ticket demand overprices them. This is
also the one factor this repo has *measured on its own data*: the
walk-forward backtest's top-10 portfolio ran beta 1.68 with negative CAPM
alpha, and every variant that lowered beta improved cumulative return —
volatility drag (~sigma^2/2 per period) was the dominant cost.

Subscores, both lower-is-better:
- beta vs the benchmark (QQQ) over the trailing year;
- idiosyncratic volatility — std dev of daily returns after removing the
  beta * benchmark component (falls back to total volatility when the
  benchmark series is unavailable).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import combine_subscores, percentile_score

MIN_DAYS = 126  # need ~6 months of dailies for a usable beta


def beta_and_idio_vol(
    returns: pd.Series, bench_returns: pd.Series | None
) -> tuple[float, float]:
    """(beta, idio_vol) from aligned daily returns; (nan, total_vol) without
    a benchmark."""
    r = returns.dropna()
    if len(r) < MIN_DAYS:
        return (np.nan, np.nan)
    if bench_returns is None:
        return (np.nan, float(r.std()))
    joined = pd.concat([r, bench_returns], axis=1, join="inner").dropna()
    if len(joined) < MIN_DAYS:
        return (np.nan, float(r.std()))
    rr, rb = joined.iloc[:, 0], joined.iloc[:, 1]
    var_b = float(rb.var())
    if var_b <= 0:
        return (np.nan, float(rr.std()))
    beta = float(rr.cov(rb) / var_b)
    resid = rr - beta * rb
    return (beta, float(resid.std()))


def score(
    price_history: pd.DataFrame, bench_close: pd.Series | None = None
) -> pd.Series:
    closes = price_history["Close"]
    bench_returns = (
        bench_close.pct_change().dropna() if bench_close is not None else None
    )

    rows = {}
    for ticker in closes.columns:
        returns = closes[ticker].pct_change()
        b, iv = beta_and_idio_vol(returns, bench_returns)
        rows[ticker] = {"beta": b, "idio_vol": iv}
    feats = pd.DataFrame.from_dict(rows, orient="index")
    if feats.empty:
        return pd.Series(dtype=float)

    subs = pd.DataFrame(index=feats.index)
    subs["beta"] = percentile_score(feats["beta"], higher_is_better=False)
    subs["idio_vol"] = percentile_score(feats["idio_vol"], higher_is_better=False)
    return combine_subscores(subs)
