"""Insider signal: recent Form 4 filing intensity, percentile-ranked 0-100.

v1 scores on filing *count* in the lookback window (a liquid proxy for insider
attention). Parsing each filing's XML for buy-vs-sell direction and dollar
size is the natural v1.1 upgrade and slots in here without touching callers.
"""

from __future__ import annotations

import pandas as pd

from .base import percentile_score


def score(form4_counts: dict[str, int | None]) -> pd.Series:
    s = pd.Series(form4_counts, dtype="float64")
    # None (fetch failure) stays NaN -> 'no information' in the composite.
    return percentile_score(s)
