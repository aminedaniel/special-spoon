"""Profitability signal: GP/A ranks up, asset growth ranks down."""

import numpy as np
import pandas as pd

from stock_selector.signals import profitability


def _metrics(rows: dict[str, tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        {t: {"gp_over_assets": g, "asset_growth": a} for t, (g, a) in rows.items()}
    ).T


def test_high_gp_low_growth_wins():
    scores = profitability.score(_metrics({
        "GOOD": (0.55, 0.02),    # very profitable, barely growing assets
        "MID": (0.30, 0.15),
        "BAD": (0.05, 0.80),     # unprofitable empire-builder
    }))
    assert scores["GOOD"] > scores["MID"] > scores["BAD"]


def test_missing_statements_stay_nan():
    scores = profitability.score(_metrics({
        "A": (0.4, 0.1),
        "B": (0.2, 0.3),
        "NODATA": (None, None),
    }))
    assert np.isnan(scores["NODATA"])
    assert scores["A"] > scores["B"]


def test_partial_data_scores_on_what_exists():
    # Only asset growth known -> still scored on that one factor.
    scores = profitability.score(_metrics({
        "A": (None, 0.05),
        "B": (None, 0.60),
    }))
    assert scores["A"] > scores["B"]
