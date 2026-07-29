"""Indicator math checks against hand-computable cases."""

import numpy as np
import pandas as pd

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
