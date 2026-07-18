"""Corporate-event signal: 13D/13G stakes minus shelf/red-flag filings.

Event points are already signed; percentile-rank them so a shortlist where
nobody has events scores everyone neutral, and only real filings separate
names.
"""

from __future__ import annotations

import pandas as pd

from .base import percentile_score


def score(points: dict[str, float | None]) -> pd.Series:
    s = pd.Series(points, dtype="float64")
    return percentile_score(s)
