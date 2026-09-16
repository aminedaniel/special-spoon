"""Residual momentum: beta-adjusted 12-1 momentum, tracked but not scored."""

import numpy as np
import pandas as pd

from stock_selector.signals.residual_momentum import residual_momentum, score


def _bench(n=300, drift=0.0008, seed=1):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(drift, 0.010, n))


def _stock(bench, beta=1.4, seed=2):
    """A benchmark exposure plus a real idiosyncratic component, which every
    actual stock has and which the signal needs in order to mean anything."""
    rng = np.random.default_rng(seed)
    return bench * beta + pd.Series(rng.normal(0.0, 0.012, len(bench)))


def test_beta_exposure_is_removed_while_raw_momentum_keeps_it():
    """The whole point (Blitz/Huij/Martens): in a rising market a high-beta
    name accumulates raw momentum it did not earn idiosyncratically.

    The benchmark gets a deterministic uptrend plus genuine variance: a random
    path's realized return over the 12-1 window can come out negative, which
    inverts the premise instead of testing it, while a perfectly flat series
    has no variance for a beta to be estimated against."""
    rng = np.random.default_rng(11)
    bench = pd.Series(0.0012 + rng.normal(0.0, 0.006, 300))
    assert bench.iloc[-252:-21].sum() > 0.15      # the market really did rise
    high, low = _stock(bench, beta=2.0, seed=3), _stock(bench, beta=0.5, seed=3)

    # Identical idiosyncratic path; the ONLY difference is beta.
    raw_gap = high.iloc[-252:-21].sum() - low.iloc[-252:-21].sum()
    assert raw_gap > 0.25          # raw momentum separates them by 25pp

    res_gap = residual_momentum(high, bench) - residual_momentum(low, bench)
    assert abs(res_gap) < 1e-6     # residual momentum sees through it entirely


def test_a_name_that_is_only_beta_is_undefined_not_extreme():
    """Returns that are an exact multiple of the benchmark leave residuals at
    floating-point noise, and noise/noise is an arbitrary number of order one.
    Measured before the guard existed: exactly 1.8x the benchmark scored 9.92,
    which would have ranked top of the cross-section on nothing at all."""
    bench = _bench()
    assert np.isnan(residual_momentum(bench * 1.8, bench))


def test_idiosyncratic_drift_is_detected_net_of_beta():
    """Two names with the SAME beta and the same noise, one with a positive
    residual drift inside the 12-1 window."""
    bench = _bench()
    flat = _stock(bench)
    drifter = flat.copy()
    drifter.iloc[-252:-21] += 0.0015
    assert residual_momentum(drifter, bench) > residual_momentum(flat, bench)


def test_recent_month_cannot_influence_the_score_at_all():
    """The reversal month is dropped BEFORE the beta is estimated, so a move
    confined to it is invisible — not merely damped. Estimating beta over a
    window that included the month would let it shift every residual in the
    ranking window, leaking the month back in through the regression."""
    bench = _bench()
    base = _stock(bench)
    late_move = base.copy()
    late_move.iloc[-21:] += 0.02
    assert residual_momentum(late_move, bench) == residual_momentum(base, bench)


def test_no_benchmark_gives_nan_not_a_fallback():
    """Without a benchmark there is no residual. Falling back to raw momentum
    would silently duplicate the technical signal and report it as a second,
    agreeing opinion."""
    bench = _bench()
    assert np.isnan(residual_momentum(_stock(bench), None))


def test_short_history_is_nan():
    bench = _bench(n=100)
    assert np.isnan(residual_momentum(_stock(bench), bench))


def test_score_ranks_cross_sectionally(price_history):
    bench_returns = _bench(n=len(price_history))
    bench_close = pd.Series(
        ((1 + bench_returns).cumprod() * 100).values, index=price_history.index
    )
    scores = score(price_history, bench_close)
    graded = scores.dropna()
    assert not graded.empty
    assert graded.between(0, 100).all()


def test_score_is_all_nan_without_a_benchmark(price_history):
    """The column still exists — composite_score gives an unlisted category
    weight 0.0, and the scoreboard reports NaN rather than a manufactured
    rank."""
    scores = score(price_history, None)
    assert scores.isna().all()
    assert list(scores.index) == list(price_history["Close"].columns)


def test_a_benchmark_with_no_variance_is_rejected():
    """stability.beta_and_idio_vol guards with `var_b <= 0`, which a flat
    series slips past: pd.Series([0.0009] * 300).var() is 1.18e-38, not zero.
    The beta it then returns is meaningless — measured -1.81 for a series
    built with beta +2.0. The relative guard here catches it."""
    flat_bench = pd.Series([0.0009] * 300)
    rng = np.random.default_rng(3)
    stock = flat_bench * 2.0 + pd.Series(rng.normal(0.0, 0.012, 300))
    assert np.isnan(residual_momentum(stock, flat_bench))
