"""Insider signal: separate buy/sell ranking, and the scale defect it fixes."""

import numpy as np
import pandas as pd
import pytest

from stock_selector.signals.insider import BUY_SHARE, score


def _act(buy, sell):
    return {"buy_conviction": buy, "sell_pressure": sell}


def test_a_real_buyer_outranks_a_massive_seller():
    """The defect, stated as a test. Measured live, insiders sold $4.5B against
    $3.9M of buying — 1,145:1 — so netting in dollars meant a modest buy could
    never outrank a large sale. Percentile ranks put both on 0-100 first."""
    scores = score(
        {
            "BUYER": _act(50_000.0, 0.0),            # small buy, no selling
            "SELLER": _act(0.0, 500_000_000.0),      # half a billion sold
            "QUIET": _act(0.0, 0.0),
        }
    )
    assert scores["BUYER"] > scores["QUIET"] > scores["SELLER"]


def test_dollar_magnitude_cannot_dominate():
    """Scaling every sell figure by 1000x must not change the ordering — the
    old netted score would have been overwhelmed by it."""
    small = score({"A": _act(10_000.0, 1_000.0), "B": _act(0.0, 5_000.0)})
    huge = score({"A": _act(10_000.0, 1_000_000.0), "B": _act(0.0, 5_000_000.0)})
    assert list(small.sort_values().index) == list(huge.sort_values().index)


def test_buying_carries_the_larger_share():
    """Literature weighting: purchases inform, sales are largely liquidity."""
    assert BUY_SHARE > 0.5
    # A ticker top-ranked on buying and worst on selling must still beat one
    # that merely avoided selling.
    scores = score(
        {
            "ACTIVE": _act(100_000.0, 900_000.0),
            "PASSIVE": _act(0.0, 0.0),
        }
    )
    assert scores["ACTIVE"] > scores["PASSIVE"]


def test_no_buying_is_neutral_not_punished():
    """Absence of insider buying is not evidence of anything; it must sit
    mid-rank on that component rather than at the bottom."""
    tickers = "ABCDE"
    scores = score({t: _act(0.0, 0.0) for t in tickers})
    assert scores.nunique() == 1              # nothing to separate them
    # An all-tied column scores the mid-rank, (n+1)/2 / n — the middle of the
    # range, not the bottom. Ranking them last would treat "did not buy" as
    # evidence against, which no result in the literature supports.
    n = len(tickers)
    assert scores.iloc[0] == pytest.approx(((n + 1) / 2) / n * 100)


def test_missing_activity_stays_nan():
    scores = score({"KNOWN": _act(1000.0, 0.0), "UNKNOWN": None})
    assert np.isnan(scores["UNKNOWN"])
    assert not np.isnan(scores["KNOWN"])
