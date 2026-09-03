"""Net share issuance: direction, missing data, and outlier robustness."""

import numpy as np
import pandas as pd
import pytest

from stock_selector.signals.issuance import score


def test_buybacks_outrank_dilution():
    s = score(pd.Series({"BUYBACK": -0.03, "FLAT": 0.0, "DILUTER": 0.10}))
    assert s["BUYBACK"] > s["FLAT"] > s["DILUTER"]


def test_missing_stays_nan_so_the_composite_renormalizes():
    """A ticker with no share history must not be scored as if it had zero
    dilution — that would reward a data gap."""
    s = score(pd.Series({"KNOWN": 0.05, "UNKNOWN": np.nan}))
    assert np.isnan(s["UNKNOWN"])
    assert not np.isnan(s["KNOWN"])


def test_percentile_ranking_bounds_a_single_outlier():
    """One company issuing 400% of its shares must not compress everyone else
    into an indistinguishable block, which a raw z-score would do."""
    s = score(pd.Series({"A": 0.01, "B": 0.02, "C": 0.03, "EXTREME": 4.0}))
    assert s["A"] > s["B"] > s["C"] > s["EXTREME"]
    assert s["A"] - s["B"] == pytest.approx(s["B"] - s["C"])


def test_none_yields_empty_not_a_crash():
    assert score(None).empty
