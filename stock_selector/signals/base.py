"""Shared normalization utilities for signal scores.

Every signal category produces a 0-100 score per ticker via cross-sectional
percentile ranking, so categories are directly comparable before weighting.
"""

from __future__ import annotations

import pandas as pd


def percentile_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Rank values cross-sectionally into a 0-100 score.

    NaNs stay NaN (the caller decides how to handle missing sub-signals).
    """
    ranked = series.rank(pct=True, ascending=higher_is_better)
    return ranked * 100.0


def combine_subscores(subscores: pd.DataFrame) -> pd.Series:
    """Average the available sub-signal scores per ticker, ignoring NaNs.

    A ticker missing every sub-signal gets NaN, which the composite treats
    as 'no information' rather than zero.
    """
    return subscores.mean(axis=1, skipna=True)
