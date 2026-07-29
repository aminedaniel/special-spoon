"""Earnings-drift signal (PEAD): standardized earnings surprise, 0-100.

Ranks tickers by their most recent in-window standardized surprise (SUE).
A ticker with no reported announcement inside the drift window is NaN —
no information, weight redistributes — rather than punished.

Of everything in the composite this has the strongest academic paper trail:
documented in 1968, still measurable post-publication, and strongest exactly
where this screen lives (small caps with thin analyst coverage underreact
the most).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import percentile_score


def score(surprises: dict[str, dict | None]) -> pd.Series:
    sue = pd.Series(
        {
            t: (s["sue"] if s is not None else np.nan)
            for t, s in surprises.items()
        },
        dtype="float64",
    )
    return percentile_score(sue)
