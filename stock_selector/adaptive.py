"""Adaptive signal reweighting: tilt weights toward signals that have been
predicting returns, with guardrails so noise can't whipsaw the strategy.

Success metric: information coefficient (IC) — Spearman rank correlation
between a signal's scores on a report date and the realized forward returns
of those tickers. IC ~ 0 means no predictive power; sustained positive IC
means the signal has been finding winners.

Guardrails:
  - no tilting until `min_periods` graded reports exist (small samples lie);
  - the tilt is a bounded multiplier (1 +/- max_tilt), never a takeover;
  - shrinkage: measured IC is blended toward zero by `shrinkage` before use,
    so weights drift with evidence instead of chasing the latest week;
  - floor: no signal drops below `floor_frac` of its base weight — a signal
    in a cold streak keeps enough weight to prove itself again;
  - weights renormalize to sum to 1.
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

MIN_PERIODS = 6       # graded reports required before any tilting
SHRINKAGE = 0.5       # halve measured IC before applying (regression to mean)
IC_SCALE = 0.10       # |IC| producing a full tilt (0.10 is a strong IC)
MAX_TILT = 0.5        # weight multiplier bounded to [1-MAX_TILT, 1+MAX_TILT]
FLOOR_FRAC = 0.25     # min fraction of base weight a signal can fall to


def signal_ic(scores: pd.DataFrame, forward_returns: pd.Series) -> pd.Series:
    """Per-signal Spearman IC for one report: `scores` has one column per
    signal (score_-prefixed or bare), rows = tickers; `forward_returns`
    aligns on ticker index."""
    out = {}
    returns = forward_returns.dropna()
    for col in scores.columns:
        name = col.removeprefix("score_")
        s = scores[col].reindex(returns.index).dropna()
        if len(s) < 5 or s.nunique() < 2:
            continue
        # Spearman = Pearson on ranks (avoids a scipy dependency)
        r = returns.reindex(s.index)
        out[name] = float(s.rank().corr(r.rank()))
    return pd.Series(out, dtype="float64")


def adapt_weights(
    base_weights: dict[str, float],
    ic_history: pd.DataFrame,
    min_periods: int = MIN_PERIODS,
    shrinkage: float = SHRINKAGE,
    ic_scale: float = IC_SCALE,
    max_tilt: float = MAX_TILT,
    floor_frac: float = FLOOR_FRAC,
) -> dict[str, float]:
    """Tilt base weights by trailing mean IC per signal.

    `ic_history`: rows = report dates, columns = signal names, values = IC.
    Signals without enough history keep their base weight (tilt 1.0).
    """
    adapted: dict[str, float] = {}
    for name, base in base_weights.items():
        tilt = 1.0
        if name in ic_history.columns:
            ics = ic_history[name].dropna()
            if len(ics) >= min_periods:
                mean_ic = float(ics.mean()) * (1.0 - shrinkage)
                tilt += max(-max_tilt, min(max_tilt, mean_ic / ic_scale))
        adapted[name] = max(base * tilt, base * floor_frac)

    total = sum(adapted.values())
    adapted = {k: v / total for k, v in adapted.items()}
    log.info(
        "adaptive weights: %s",
        {k: round(v, 3) for k, v in adapted.items()},
    )
    return adapted
