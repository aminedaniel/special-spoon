"""Profitability signal: gross profitability + (negative) asset growth, 0-100.

Two of the best-replicated cross-sectional factors, both cheap to compute:

- Gross profitability (Novy-Marx 2013): gross profit / total assets. "The
  other side of value" — profitable firms outperform, and gross profit is a
  cleaner quality measure than ROE because it sits above the accrual and
  financing choices that pollute net income.
- Asset growth (Cooper/Gulen/Schill 2008): firms growing their balance sheet
  fastest underperform — empire-building and heavy issuance are financed at
  exactly the wrong times. Lower is better; it became the CMA factor.

Kept separate from `fundamentals` so the IC machinery grades these factors
on their own record instead of blending them into the growth/leverage mix.
"""

from __future__ import annotations

import pandas as pd

from .base import combine_subscores, percentile_score


def score(metrics: pd.DataFrame) -> pd.Series:
    subs = pd.DataFrame(index=metrics.index)
    subs["gp_over_assets"] = percentile_score(
        pd.to_numeric(metrics.get("gp_over_assets"), errors="coerce")
    )
    subs["asset_growth"] = percentile_score(
        pd.to_numeric(metrics.get("asset_growth"), errors="coerce"),
        higher_is_better=False,
    )
    return combine_subscores(subs)
