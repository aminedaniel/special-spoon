"""Stability signal: low-beta/low-vol names rank above high-beta ones."""

import numpy as np
import pandas as pd

from stock_selector.signals.stability import beta_and_idio_vol, score


def _prices(days: int = 260, seed: int = 7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end="2026-07-17", periods=days)
    bench_ret = rng.normal(0.0004, 0.010, size=days)
    bench = pd.Series(100 * np.exp(np.cumsum(bench_ret)), index=idx)

    frames = {}
    # CALM tracks the benchmark at half beta with tiny noise; WILD at 2x
    # beta with heavy idiosyncratic noise.
    for name, beta, noise in [("CALM", 0.5, 0.002), ("WILD", 2.0, 0.03)]:
        ret = beta * bench_ret + rng.normal(0, noise, size=days)
        frames[("Close", name)] = 100 * np.exp(np.cumsum(ret))
        frames[("Volume", name)] = np.full(days, 1e5)
    df = pd.DataFrame(frames, index=idx)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df, bench


def test_beta_estimate_recovers_construction():
    prices, bench = _prices()
    returns = prices["Close"]["WILD"].pct_change()
    beta, idio = beta_and_idio_vol(returns, bench.pct_change().dropna())
    assert 1.6 < beta < 2.4          # built at 2.0
    assert idio > 0.02               # heavy idiosyncratic noise survives


def test_calm_outranks_wild():
    prices, bench = _prices()
    scores = score(prices, bench)
    assert scores["CALM"] > scores["WILD"]


def test_no_benchmark_falls_back_to_total_vol():
    prices, _ = _prices()
    scores = score(prices, bench_close=None)
    # beta column is all-NaN, so ranking rests on volatility alone
    assert scores["CALM"] > scores["WILD"]


def test_short_history_is_nan():
    prices, bench = _prices(days=60)
    scores = score(prices, bench)
    assert scores.isna().all()
