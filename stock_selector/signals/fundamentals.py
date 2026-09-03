"""Fundamentals signal: growth + balance-sheet quality, 0-100.

Valuation multiples (P/E, P/S, EV/…) live in the separate `valuation` signal,
so this category isn't double-counting cheapness — it scores business quality
(growth, returns, leverage, margins) independent of price.

Dividend yield used to be a fifth sub-score and was removed. Its docstring
called it a "small weightless bonus", but the code gave it a full 1/5 of the
category — and `.fillna(0.0)` meant it was never NaN, so unlike every other
sub-score it could not drop out for a ticker that lacked it. In a universe of
small/mid-cap tech most names pay nothing, so the whole non-paying cohort tied
at one shared rank and the sub-score degenerated into a near-binary "pays a
dividend" flag carrying 20% of the weight. It also appears in none of the
factor literature this project cites, and for growth-stage tech a payout is
at best ambiguous — it signals a company with fewer places to reinvest.
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

    return combine_subscores(subs).replace([np.inf, -np.inf], np.nan)
