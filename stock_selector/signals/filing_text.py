"""Filing-language stability signal ("lazy prices"): higher similarity
between consecutive periodic reports scores better — quiet filings are a
documented positive, heavy rewrites a warning."""

from __future__ import annotations

import pandas as pd

from .base import percentile_score


def score(similarity: dict[str, float | None]) -> pd.Series:
    s = pd.Series(similarity, dtype="float64")
    return percentile_score(s)
