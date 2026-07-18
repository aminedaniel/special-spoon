"""Congressional trading signal: net disclosed buying, percentile-ranked 0-100."""

from __future__ import annotations

import pandas as pd

from .base import percentile_score


def score(activity: dict[str, dict[str, int]]) -> pd.Series:
    """Net buys (buys - sells) per ticker, ranked cross-sectionally.

    Tickers with zero disclosed activity all share the same neutral rank —
    only actual congressional buying/selling separates names.
    """
    net = pd.Series(
        {t: c.get("buys", 0) - c.get("sells", 0) for t, c in activity.items()},
        dtype="float64",
    )
    return percentile_score(net)
