"""Insider signal: net open-market Form 4 dollars, percentile-ranked 0-100.

Scores on net_dollars (open-market purchases minus sales by insiders), so a
cluster of real buys ranks above routine selling — filing count alone can't
tell those apart.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import percentile_score


def score(activity: dict[str, dict | None]) -> pd.Series:
    net = pd.Series(
        {
            t: (a["net_dollars"] if a is not None else np.nan)
            for t, a in activity.items()
        },
        dtype="float64",
    )
    # None (fetch failure / unknown CIK) stays NaN -> 'no information'.
    return percentile_score(net)
