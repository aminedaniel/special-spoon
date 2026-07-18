"""Indicator math checks against hand-computable cases."""

import numpy as np
import pandas as pd

from stock_selector.signals.technical import rsi, score


def test_rsi_all_gains_is_100():
    close = pd.Series(np.arange(1.0, 40.0))  # strictly rising
    assert rsi(close).iloc[-1] == 100.0


def test_rsi_all_losses_near_zero():
    close = pd.Series(np.arange(40.0, 1.0, -1.0))  # strictly falling
    assert rsi(close).iloc[-1] < 1.0


def test_rsi_alternating_is_moderate():
    # Equal up/down moves -> RSI near 50
    moves = np.tile([1.0, -1.0], 50)
    close = pd.Series(100 + np.cumsum(moves))
    value = rsi(close).iloc[-1]
    assert 40 <= value <= 60


def test_score_ranks_uptrend_over_downtrend(price_history):
    scores = score(price_history)
    # conftest builds AAAA with the strongest drift, EEEE the weakest
    assert scores["AAAA"] > scores["EEEE"]
    assert scores.between(0, 100).all()


def test_score_skips_short_history(price_history):
    truncated = price_history.iloc[-30:]  # < 6 months of data
    scores = score(truncated)
    assert scores.dropna().empty
