"""Adaptive reweighting: IC math and guardrail behavior."""

import numpy as np
import pandas as pd
import pytest

from stock_selector.adaptive import adapt_weights, signal_ic

BASE = {"technical": 0.5, "insider": 0.25, "events": 0.25}


def test_signal_ic_perfect_and_inverse():
    scores = pd.DataFrame(
        {
            "score_good": [10, 20, 30, 40, 50],
            "score_bad": [50, 40, 30, 20, 10],
        },
        index=list("abcde"),
    )
    returns = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05], index=list("abcde"))
    ics = signal_ic(scores, returns)
    assert ics["good"] == pytest.approx(1.0)
    assert ics["bad"] == pytest.approx(-1.0)


def test_signal_ic_skips_tiny_samples():
    scores = pd.DataFrame({"score_x": [1, 2]}, index=["a", "b"])
    returns = pd.Series([0.1, 0.2], index=["a", "b"])
    assert signal_ic(scores, returns).empty


def _ic_history(values: dict[str, float], periods: int) -> pd.DataFrame:
    return pd.DataFrame([values] * periods)


def test_adapt_weights_needs_min_periods():
    history = _ic_history({"technical": 0.5}, periods=3)  # below MIN_PERIODS
    out = adapt_weights(BASE, history)
    assert out == pytest.approx(BASE)


def test_adapt_weights_tilts_toward_success():
    history = _ic_history({"technical": 0.10, "insider": -0.10, "events": 0.0}, 10)
    out = adapt_weights(BASE, history)
    assert out["technical"] > BASE["technical"]
    assert out["insider"] < BASE["insider"]
    assert sum(out.values()) == pytest.approx(1.0)


def test_adapt_weights_tilt_is_bounded():
    # Absurd IC must not let one signal take over or another die.
    history = _ic_history({"technical": 5.0, "insider": -5.0, "events": 0.0}, 10)
    out = adapt_weights(BASE, history)
    assert out["technical"] <= BASE["technical"] * 1.5 / 0.9  # cap + renorm slack
    assert out["insider"] >= BASE["insider"] * 0.25 / 1.5     # floor + renorm slack
    assert sum(out.values()) == pytest.approx(1.0)


def test_adapt_weights_unknown_signal_keeps_base():
    history = _ic_history({"mystery": 0.5}, 10)
    out = adapt_weights(BASE, history)
    assert out == pytest.approx(BASE)
