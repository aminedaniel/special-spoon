"""Fundamentals signal: growth + balance-sheet quality, 0-100.

Valuation multiples (P/E, P/S, EV/…) live in the separate `valuation` signal,
so this category isn't double-counting cheapness — it scores business quality
(growth, returns, leverage, margins) independent of price.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import combine_subscores, percentile_score


def score(fundamentals: pd.DataFrame) -> pd.Series:
    """Score business quality cross-sectionally (price/valuation excluded).

    Sub-signals (each percentile-ranked, then averaged):
      - revenueGrowth: higher is better
      - debtToEquity: lower is better
      - returnOnEquity: higher is better
      - grossMargins: higher is better
      - dividendYield: higher is better (small weightless bonus for cash return)
    """
    f = fundamentals

    subs = pd.DataFrame(index=f.index)
    subs["revenue_growth"] = percentile_score(
        pd.to_numeric(f.get("revenueGrowth"), errors="coerce")
    )
    subs["debt_to_equity"] = percentile_score(
        pd.to_numeric(f.get("debtToEquity"), errors="coerce"), higher_is_better=False
    )
    subs["roe"] = percentile_score(
        pd.to_numeric(f.get("returnOnEquity"), errors="coerce")
    )
    subs["gross_margins"] = percentile_score(
        pd.to_numeric(f.get("grossMargins"), errors="coerce")
    )
    subs["dividend_yield"] = percentile_score(
        pd.to_numeric(f.get("dividendYield"), errors="coerce").fillna(0.0)
    )

    return combine_subscores(subs).replace([np.inf, -np.inf], np.nan)
