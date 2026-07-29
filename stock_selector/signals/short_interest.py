"""Short-interest signal: heavily shorted names score low, 0-100.

The mean effect, not the squeeze tail: Boehmer, Jones & Zhang (and a long
line since) find that high short interest predicts *negative* returns —
short sellers are the best-informed traders in the market, and expensive-to-
short small caps are where their information is least arbitraged away. The
retail framing ("high short interest = squeeze fuel") bets on the tail event
and loses the average.

Two subscores, both lower-is-better:
- shortPercentOfFloat — the level of bearish positioning;
- MoM change in shares short — shorts piling in is worse than a static base.

Data rides along in the Ticker.info batch already fetched for fundamentals
(sourced from the exchanges' twice-monthly reports), so this is Stage A and
costs nothing extra. Names with no reported short data stay NaN.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import combine_subscores, percentile_score


def score(fundamentals: pd.DataFrame) -> pd.Series:
    f = fundamentals
    pct_float = pd.to_numeric(f.get("shortPercentOfFloat"), errors="coerce")
    shares = pd.to_numeric(f.get("sharesShort"), errors="coerce")
    prior = pd.to_numeric(f.get("sharesShortPriorMonth"), errors="coerce")

    subs = pd.DataFrame(index=f.index)
    subs["pct_of_float"] = percentile_score(pct_float, higher_is_better=False)
    change = (shares / prior.where(prior > 0) - 1.0).replace(
        [np.inf, -np.inf], np.nan
    )
    subs["mom_change"] = percentile_score(change, higher_is_better=False)
    return combine_subscores(subs)
