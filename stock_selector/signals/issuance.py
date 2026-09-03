"""Net share issuance: trailing change in shares outstanding, LOWER is better.

Split out of `quality` because it is not the same kind of evidence as accruals
and should not silently share a weight with it.

Of everything in this table, issuance has the strongest replication record.
Pontiff & Woodgate (2008) and Daniel & Titman (2006) established that share
issuance predicts the cross-section; more importantly, when Hou, Xue & Zhang
(2020) re-tested 452 published anomalies with NYSE breakpoints and value
weighting and found roughly 65% failed to clear significance, issuance-related
anomalies were among the categories that survived best. Its former partner,
Sloan's accruals anomaly, went the other way — Green, Hand & Soliman (2011)
found it had largely disappeared from US equities post-publication. Averaging a
survivor with a casualty at 50/50 and calling the result one signal obscured
both.

The economics are also sharper in this universe than in a broad one. Small and
mid-cap tech funds itself substantially with stock, so share counts drift up a
few percent a year through compensation alone. That is a genuine transfer from
existing holders which GAAP earnings do not charge against income, and it is
invisible to every other signal here.

Direction: buybacks shrink the count (good), issuance and stock-comp bloat
expand it (bad). Scored by percentile rank so the magnitude of any single
outlier cannot dominate.

NOT YET VALIDATED on this universe — see the backtest. It is, however, the only
fundamentals-family signal that CAN be validated here: get_shares_full returns
dated history rather than the current-snapshot fields that force fundamentals,
valuation and quality out of the walk-forward as lookahead.
"""

from __future__ import annotations

import pandas as pd

from .base import percentile_score


def score(share_change: pd.Series | None) -> pd.Series:
    """Rank trailing share-count change, lower better. NaN stays NaN so the
    composite renormalizes over the categories a ticker actually has."""
    if share_change is None:
        return pd.Series(dtype="float64")
    return percentile_score(
        pd.to_numeric(share_change, errors="coerce"), higher_is_better=False
    )
