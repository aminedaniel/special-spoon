"""Insider signal: shaped open-market Form 4 dollars, percentile-ranked 0-100.

Ranks `signal_dollars` from window_activity: officer buys weighted above
director buys, a cluster multiplier when several distinct insiders bought,
and sells discounted to a fraction — because purchases carry the information
while sales are mostly liquidity/diversification/10b5-1 noise. The raw
buys-minus-sells figure still travels alongside for honest reporting.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import percentile_score


def score(activity: dict[str, dict | None]) -> pd.Series:
    shaped = pd.Series(
        {
            t: (a["signal_dollars"] if a is not None else np.nan)
            for t, a in activity.items()
        },
        dtype="float64",
    )
    # None (fetch failure / unknown CIK) stays NaN -> 'no information'.
    return percentile_score(shaped)
