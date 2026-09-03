"""Insider signal: buying and selling ranked separately, then combined.

Netting them in dollars did not work, and the reason is arithmetic rather than
a matter of taste. Measured over 38 tickers and a year
(scripts/diagnose_insider_window.py), insiders bought $3.9M and sold $4.5B — a
ratio of about 1,145 to 1. The previous score subtracted 0.25 x sells from
weighted buys in raw dollars, so even at a quarter weight the sell term was
around two orders of magnitude larger in aggregate. Whatever that ranking
measured, it was not insider buying: it was "minus discretionary sells", with
the buy component as imperceptible noise on top.

That inverted the literature. Lakonishok & Lee (2001) and Jeng, Metrick &
Zeckhauser (2003) find open-market PURCHASES carry the information, while sales
are largely liquidity, diversification and tax-driven — which is why 10b5-1
plan trades are already excluded upstream. The component with the evidence
behind it was the one that could not influence the result.

The fix is to rank each side across the cross-section first. Percentile ranks
are 0-100 by construction, so a billion dollars of selling and a hundred
thousand of buying arrive on the same scale and the weighting below decides
their influence — not the units. Buying carries BUY_SHARE of the combined
score, selling the remainder, which puts the emphasis where the evidence is.

A ticker with no buying sits mid-rank on the buy component rather than at the
bottom: absence of insider buying is neutral information, not a negative, and
the literature gives no basis for punishing it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import percentile_score

# Buying carries three quarters of the signal. Sales are not ignored outright —
# heavy discretionary selling is weak evidence rather than no evidence — but
# they can no longer outvote the component the research actually supports.
BUY_SHARE = 0.75


def _component(activity: dict[str, dict | None], key: str) -> pd.Series:
    return pd.Series(
        {t: (a[key] if a is not None else np.nan) for t, a in activity.items()},
        dtype="float64",
    )


def score(activity: dict[str, dict | None]) -> pd.Series:
    """Rank buy conviction and sell pressure separately, then blend.

    None (fetch failure / unknown CIK) stays NaN — 'no information' — so the
    composite renormalizes over the categories a ticker actually has.
    """
    buy_rank = percentile_score(_component(activity, "buy_conviction"))
    sell_rank = percentile_score(
        _component(activity, "sell_pressure"), higher_is_better=False
    )
    return BUY_SHARE * buy_rank + (1.0 - BUY_SHARE) * sell_rank
