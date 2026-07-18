"""Composite scoring: quality gate, weighted combination, ranking."""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)


def apply_quality_gate(
    fundamentals: pd.DataFrame, thresholds: dict[str, float]
) -> pd.DataFrame:
    """Filter the universe on market-cap band and extreme multiples.

    A missing P/E passes the gate (unprofitable growth names are common in
    small/mid-cap tech); only an extreme *known* P/E is excluded.
    """
    f = fundamentals
    cap = pd.to_numeric(f.get("marketCap"), errors="coerce")
    pe = pd.to_numeric(f.get("trailingPE"), errors="coerce")

    mask = pd.Series(True, index=f.index)
    if "min_market_cap" in thresholds:
        mask &= cap >= thresholds["min_market_cap"]
    if "max_market_cap" in thresholds:
        mask &= cap <= thresholds["max_market_cap"]
    if "max_pe" in thresholds:
        mask &= pe.isna() | (pe <= thresholds["max_pe"])

    gated = f[mask]
    log.info("quality gate: %d/%d tickers pass", len(gated), len(f))
    return gated


def composite_score(
    category_scores: dict[str, pd.Series], weights: dict[str, float]
) -> pd.DataFrame:
    """Weighted combination of 0-100 category scores into a ranked frame.

    Missing categories for a ticker are treated as 'no information': the
    remaining weights are renormalized over the categories that ARE present,
    so a ticker isn't punished for e.g. having no insider filings this week.

    Returns a DataFrame indexed by ticker with one column per category
    (`score_<name>`), a `composite` column, and a `rank` column (1 = best).
    """
    scores = pd.DataFrame(
        {name: s for name, s in category_scores.items()}
    )

    weight_row = pd.Series({name: weights.get(name, 0.0) for name in scores.columns})
    present = scores.notna()
    # Effective weight per ticker/category, zeroed where the score is missing,
    # then renormalized so each ticker's present-category weights sum to 1.
    eff = present.mul(weight_row, axis=1)
    eff_total = eff.sum(axis=1)
    eff = eff.div(eff_total.where(eff_total > 0), axis=0)

    composite = (scores.fillna(0.0) * eff).sum(axis=1)
    composite[eff_total == 0] = float("nan")

    out = scores.add_prefix("score_")
    out["composite"] = composite
    out = out.sort_values("composite", ascending=False)
    out["rank"] = range(1, len(out) + 1)
    return out
