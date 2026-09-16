"""Indicator math checks against hand-computable cases."""

import numpy as np
import pandas as pd
import pytest

from stock_selector.signals.technical import momentum_12_1, score


def test_momentum_12_1_hand_computed():
    # 300 days doubling linearly; 12-1 momentum ends at day -21, bases at -252.
    close = pd.Series(np.linspace(100.0, 200.0, num=300))
    expected = close.iloc[-21] / close.iloc[-252] - 1
    assert momentum_12_1(close) == expected


def test_momentum_12_1_short_history_clamps_to_start():
    close = pd.Series(np.linspace(100.0, 150.0, num=180))
    expected = close.iloc[-21] / close.iloc[0] - 1
    assert momentum_12_1(close) == expected


def test_momentum_12_1_ignores_last_month_crash():
    """A crash entirely inside the most recent month must not change 12-1
    momentum — that window is excluded by construction (short-term reversal)."""
    steady = pd.Series(np.linspace(100.0, 200.0, num=300))
    crashed = steady.copy()
    crashed.iloc[-20:] = 50.0  # collapse strictly inside the skipped month
    assert momentum_12_1(crashed) == momentum_12_1(steady)


def test_score_ranks_uptrend_over_downtrend(price_history):
    scores = score(price_history)
    # conftest builds AAAA with the strongest drift, EEEE the weakest
    assert scores["AAAA"] > scores["EEEE"]
    assert scores.between(0, 100).all()


def test_score_skips_short_history(price_history):
    truncated = price_history.iloc[-30:]  # < 6 months of data
    scores = score(truncated)
    assert scores.dropna().empty


def test_features_are_exactly_the_two_with_a_published_record(price_history):
    """The signal averages its features equally, so an unevidenced feature is
    not harmless — it dilutes the evidenced ones in proportion. Three folklore
    trend/volume features used to carry 3/5 of this signal (0.15 of the whole
    composite). This pins the set so they cannot drift back in unnoticed."""
    from stock_selector.signals.technical import _per_ticker_features

    feats = _per_ticker_features(price_history["Close"]["AAAA"])
    assert set(feats) == {"mom_12_1", "breakout_proximity"}


def test_breakout_proximity_is_zero_at_the_52_week_high():
    """Defined as a distance below the high, so it is <= 0 and closer to 0 is
    better. A series ending at its high must sit exactly at 0."""
    from stock_selector.signals.technical import _per_ticker_features

    rising = pd.Series(np.linspace(100.0, 200.0, num=300))
    assert _per_ticker_features(rising)["breakout_proximity"] == 0.0

    # Same path, then a 20% drawdown off the high. Note the high must be taken
    # AFTER the edit: overwriting the last point removes the old maximum, so
    # the 52-week high becomes the prior bar.
    pulled_back = rising.copy()
    pulled_back.iloc[-1] = rising.iloc[-2] * 0.8
    assert _per_ticker_features(pulled_back)["breakout_proximity"] == pytest.approx(-0.2)


def test_score_does_not_need_a_volume_panel(price_history):
    """Volume fed only the removed volume_trend feature. Dropping the read
    keeps the signal working on a Close-only frame."""
    close_only = price_history[["Close"]]
    scores = score(close_only)
    assert scores.notna().any()
    assert scores.between(0, 100).all()
