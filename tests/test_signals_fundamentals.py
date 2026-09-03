"""Fundamentals composition — and the dividend sub-score that used to distort it."""

import numpy as np
import pandas as pd
import pytest

from stock_selector.signals import fundamentals as fundamentals_signal


def _frame(rows: dict) -> pd.DataFrame:
    return pd.DataFrame(rows).T


def test_dividend_yield_no_longer_affects_the_score():
    """Two companies identical on every business-quality metric must score
    identically. Dividend policy is not part of this category any more: it was
    a full 1/5 of the score, and for growth-stage tech a payout is at best
    ambiguous — it marks a company with fewer places to reinvest."""
    base = {
        "revenueGrowth": 0.30, "debtToEquity": 40.0,
        "returnOnEquity": 0.18, "grossMargins": 0.65,
    }
    scores = fundamentals_signal.score(
        _frame({
            "PAYER": {**base, "dividendYield": 0.04},
            "NOPAY": {**base, "dividendYield": None},
        })
    )
    assert scores["PAYER"] == pytest.approx(scores["NOPAY"])


def test_non_payers_are_no_longer_collapsed_into_one_tied_block():
    """The failure mode being removed. `.fillna(0.0)` meant the sub-score was
    never NaN, so in a universe where most names pay nothing the whole
    non-paying cohort shared one rank — a near-binary 'pays a dividend' flag
    carrying 20% of the weight. Ordering must now come from the real metrics."""
    frame = _frame({
        "BEST":  {"revenueGrowth": 0.50, "debtToEquity": 10.0,
                  "returnOnEquity": 0.30, "grossMargins": 0.80,
                  "dividendYield": None},
        "MID":   {"revenueGrowth": 0.25, "debtToEquity": 60.0,
                  "returnOnEquity": 0.15, "grossMargins": 0.55,
                  "dividendYield": None},
        "WORST": {"revenueGrowth": 0.02, "debtToEquity": 200.0,
                  "returnOnEquity": 0.01, "grossMargins": 0.20,
                  # A generous payer that is worst on every real metric must
                  # still rank last; previously this bought a fifth of the score.
                  "dividendYield": 0.09},
    })
    scores = fundamentals_signal.score(frame)
    assert scores["BEST"] > scores["MID"] > scores["WORST"]
    assert scores.nunique() == 3          # no shared block


def test_missing_metric_drops_out_rather_than_scoring_zero():
    """combine_subscores averages what is present; a NaN metric must not be
    read as a bad value. This is the property dividendYield violated."""
    frame = _frame({
        "FULL": {"revenueGrowth": 0.30, "debtToEquity": 40.0,
                 "returnOnEquity": 0.18, "grossMargins": 0.65},
        "PART": {"revenueGrowth": 0.30, "debtToEquity": 40.0,
                 "returnOnEquity": None, "grossMargins": None},
    })
    scores = fundamentals_signal.score(frame)
    assert not np.isnan(scores["PART"])


def test_all_metrics_missing_is_nan_not_zero():
    frame = _frame({
        "GOOD": {"revenueGrowth": 0.30, "debtToEquity": 40.0,
                 "returnOnEquity": 0.18, "grossMargins": 0.65},
        "VOID": {"revenueGrowth": None, "debtToEquity": None,
                 "returnOnEquity": None, "grossMargins": None},
    })
    assert np.isnan(fundamentals_signal.score(frame)["VOID"])
