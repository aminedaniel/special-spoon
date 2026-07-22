"""Google Trends signal: search-interest momentum, percentile-ranked 0-100.

Higher recent-vs-baseline search interest ranks higher. This scores retail
*attention*; its predictive sign is unproven, so it carries a small base weight
and the adaptive-reweighting IC tracking validates it over time.
"""

from __future__ import annotations

import pandas as pd

from .base import percentile_score


def score(momentum: dict[str, float | None]) -> pd.Series:
    s = pd.Series(momentum, dtype="float64")
    # None (no data / throttled) stays NaN -> 'no information' in the composite.
    return percentile_score(s)
