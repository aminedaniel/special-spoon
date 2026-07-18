"""Normalization and weighted-composite behavior on synthetic data."""

import numpy as np
import pandas as pd
import pytest

from stock_selector.scoring import apply_quality_gate, composite_score
from stock_selector.signals.base import percentile_score


def test_percentile_score_ordering():
    s = pd.Series({"a": 10, "b": 20, "c": 30})
    scores = percentile_score(s)
    assert scores["c"] > scores["b"] > scores["a"]
    assert scores.max() == 100.0


def test_percentile_score_lower_is_better():
    s = pd.Series({"a": 10, "b": 20})
    scores = percentile_score(s, higher_is_better=False)
    assert scores["a"] > scores["b"]


def test_percentile_score_keeps_nan():
    s = pd.Series({"a": 1.0, "b": np.nan})
    assert np.isnan(percentile_score(s)["b"])


def test_composite_weights_applied():
    scores = {
        "x": pd.Series({"t1": 100.0, "t2": 0.0}),
        "y": pd.Series({"t1": 0.0, "t2": 100.0}),
    }
    out = composite_score(scores, {"x": 0.75, "y": 0.25})
    assert out.loc["t1", "composite"] == pytest.approx(75.0)
    assert out.loc["t2", "composite"] == pytest.approx(25.0)
    assert out.loc["t1", "rank"] == 1


def test_composite_renormalizes_missing_categories():
    # t2 has no 'y' score: its composite must use only 'x' at full weight,
    # not treat missing as zero.
    scores = {
        "x": pd.Series({"t1": 80.0, "t2": 80.0}),
        "y": pd.Series({"t1": 40.0, "t2": np.nan}),
    }
    out = composite_score(scores, {"x": 0.5, "y": 0.5})
    assert out.loc["t1", "composite"] == pytest.approx(60.0)
    assert out.loc["t2", "composite"] == pytest.approx(80.0)


def test_composite_all_missing_is_nan():
    scores = {"x": pd.Series({"t1": 50.0, "t2": np.nan})}
    out = composite_score(scores, {"x": 1.0})
    assert np.isnan(out.loc["t2", "composite"])


def test_quality_gate_cap_band_and_pe(fundamentals):
    gated = apply_quality_gate(
        fundamentals,
        {"min_market_cap": 5e8, "max_market_cap": 10e9, "max_pe": 60},
    )
    assert "EEEE" not in gated.index          # $400M < $500M floor
    assert "CCCC" in gated.index              # null PE passes the gate
    assert set(gated.index) == {"AAAA", "BBBB", "CCCC", "DDDD"}


def test_quality_gate_excludes_extreme_pe(fundamentals):
    gated = apply_quality_gate(fundamentals, {"max_pe": 30})
    assert "BBBB" not in gated.index  # PE 35 > 30
    assert "DDDD" not in gated.index  # PE 55 > 30
    assert "CCCC" in gated.index      # null PE still passes
