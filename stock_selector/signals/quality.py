"""Statement-quality signal: cashflow-vs-earnings gap and share dilution.

Sub-signals (percentile-ranked, averaged; NaN = no information):
  - accrual gap: (operating cash flow - net income) / market cap, higher
    better (earnings backed by cash beat paper earnings — Sloan's accruals
    anomaly).
  - share dilution: trailing-year change in shares outstanding, LOWER better
    (buyback shrink good, SBC-driven bloat bad).
"""

from __future__ import annotations

import pandas as pd

from .base import combine_subscores, percentile_score


def score(
    fundamentals: pd.DataFrame, share_change: pd.Series | None = None
) -> pd.Series:
    f = fundamentals
    ocf = pd.to_numeric(f.get("operatingCashflow"), errors="coerce")
    ni = pd.to_numeric(f.get("netIncomeToCommon"), errors="coerce")
    cap = pd.to_numeric(f.get("marketCap"), errors="coerce")

    subs = pd.DataFrame(index=f.index)
    subs["accrual_gap"] = percentile_score((ocf - ni) / cap)
    if share_change is not None:
        subs["dilution"] = percentile_score(
            share_change.reindex(f.index), higher_is_better=False
        )
    return combine_subscores(subs)
