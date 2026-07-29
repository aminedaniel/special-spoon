"""Valuation signal: cheap-vs-expensive within the universe, 0-100.

Cheaper multiples score higher (percentile-ranked, lower is better). Uses a
spread of multiples so the signal works across the universe — small/mid-cap
tech is full of unprofitable names where P/E is null, but EV/Sales, P/S, and
P/FCF still price them. Each ticker is scored on whatever multiples it has;
missing or non-meaningful ones (null, or negative where that's nonsensical)
simply don't contribute for that name.

Whether "cheap" actually predicts returns in tech is famously uncertain, so
this carries a modest weight and the adaptive IC tracking validates it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import combine_subscores, percentile_score


def _num(f: pd.DataFrame, name: str) -> pd.Series:
    """Column `name` as numeric, index-aligned; all-NaN if the column is absent
    (real yfinance rows sometimes omit a field)."""
    if name not in f.columns:
        return pd.Series(np.nan, index=f.index, dtype="float64")
    return pd.to_numeric(f[name], errors="coerce")


def _positive(f: pd.DataFrame, name: str) -> pd.Series:
    """Numeric column keeping only positive values (others -> NaN = no signal).

    A negative or zero multiple isn't "cheap" — it means no earnings / no
    EBITDA / negative FCF, which carries no valuation information here.
    """
    s = _num(f, name)
    return s.where(s > 0)


def score(fundamentals: pd.DataFrame) -> pd.Series:
    f = fundamentals
    cap = _positive(f, "marketCap")
    fcf = _num(f, "freeCashflow")

    subs = pd.DataFrame(index=f.index)
    # All lower-is-better: cheaper multiple -> higher score.
    subs["pe"] = percentile_score(_positive(f, "trailingPE"), higher_is_better=False)
    subs["forward_pe"] = percentile_score(
        _positive(f, "forwardPE"), higher_is_better=False
    )
    subs["ps"] = percentile_score(
        _positive(f, "priceToSalesTrailing12Months"), higher_is_better=False
    )
    subs["ev_sales"] = percentile_score(
        _positive(f, "enterpriseToRevenue"), higher_is_better=False
    )
    subs["ev_ebitda"] = percentile_score(
        _positive(f, "enterpriseToEbitda"), higher_is_better=False
    )
    subs["peg"] = percentile_score(_positive(f, "pegRatio"), higher_is_better=False)
    # Price / free cash flow: only meaningful when FCF is positive.
    pfcf = (cap / fcf.where(fcf > 0)).replace([np.inf, -np.inf], np.nan)
    subs["pfcf"] = percentile_score(pfcf, higher_is_better=False)

    return combine_subscores(subs)
