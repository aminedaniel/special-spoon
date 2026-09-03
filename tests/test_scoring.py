"""Normalization and weighted-composite behavior on synthetic data."""

import numpy as np
import pandas as pd
import pytest

from stock_selector.scoring import (
    apply_quality_gate,
    composite_score,
    degenerate_categories,
)
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


def test_percentile_score_of_constant_input_is_flat():
    """The failure this guards against: ranking an all-identical series hands
    every ticker the same mid-rank, which cannot reorder anything."""
    flat = percentile_score(pd.Series({"a": 0.0, "b": 0.0, "c": 0.0}))
    assert flat.nunique() == 1


def test_degenerate_categories_flags_constant_only():
    cats = {
        "technical": pd.Series({"a": 10.0, "b": 90.0, "c": 50.0}),
        "insider": pd.Series({"a": 50.8, "b": 50.8, "c": 50.8}),  # no activity
        "events": pd.Series({"a": np.nan, "b": 50.8, "c": 50.8}),  # constant where present
        "short_interest": pd.Series({"a": np.nan, "b": np.nan, "c": 40.0}),  # single obs, not degenerate
    }
    assert degenerate_categories(cats) == ["insider", "events"]


def test_dropping_a_degenerate_category_changes_no_order_but_frees_weight():
    varying = pd.Series({"a": 10.0, "b": 90.0})
    flat = pd.Series({"a": 50.0, "b": 50.0})
    weights = {"technical": 0.5, "insider": 0.5}

    with_flat = composite_score({"technical": varying, "insider": flat}, weights)
    without = composite_score({"technical": varying}, weights)

    # Order is identical either way — the flat category never had a say.
    assert list(with_flat.index) == list(without.index)
    # But dropping it lets the real signal carry its own full range.
    assert with_flat["composite"]["b"] == pytest.approx(70.0)
    assert without["composite"]["b"] == pytest.approx(90.0)


def test_percentile_score_is_idempotent():
    """Why re-ranking categories over the shortlist is safe: ranking an already
    ranked series reproduces it, so when the shortlist equals the gated
    universe the re-rank is exactly a no-op."""
    s = pd.Series({"a": 3.0, "b": 1.0, "c": 2.0, "d": 2.0})
    once = percentile_score(s)
    twice = percentile_score(once)
    pd.testing.assert_series_equal(once, twice)


def test_percentile_score_rescales_when_restricted_to_a_subset():
    """And why it matters once the shortlist is a strict subset: the top slice
    of a universe is compressed into the upper percentiles until re-ranked, so
    it would not share a scale with signals ranked on the subset directly."""
    universe = pd.Series({t: float(i) for i, t in enumerate("abcdefghij")})
    top3 = ["j", "i", "h"]

    sliced = percentile_score(universe).reindex(top3)
    reranked = percentile_score(percentile_score(universe).reindex(top3))

    assert sliced.min() >= 80.0            # squashed into the top of the range
    assert reranked.min() == pytest.approx(100 / 3)   # spread over the subset
    assert list(sliced.sort_values().index) == list(reranked.sort_values().index)
