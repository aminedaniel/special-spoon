"""Intangible-adjusted value: book-to-market after capitalising R&D."""

import numpy as np
import pandas as pd

from stock_selector.signals.intangible_value import (
    adjusted_book_to_market,
    knowledge_capital,
    score,
)


def test_knowledge_capital_is_straight_line_over_five_years():
    """K = R&D(t) + 0.8*R&D(t-1) + 0.6*R&D(t-2) + 0.4*R&D(t-3) + 0.2*R&D(t-4),
    newest first."""
    assert knowledge_capital([100.0] * 5) == 300.0          # 1+.8+.6+.4+.2
    assert knowledge_capital([100.0, 0.0, 0.0, 0.0, 0.0]) == 100.0
    assert knowledge_capital([0.0, 100.0, 0.0, 0.0, 0.0]) == 80.0


def test_four_years_of_statements_lose_only_the_tail():
    """Yahoo's annual income statement usually carries four years, not five.
    The missing 0.2 weight understates K by ~7% of a steady stream, and the
    filer is not rejected over it."""
    assert knowledge_capital([100.0] * 4) == 280.0
    assert 280.0 / 300.0 > 0.93


def test_extra_years_beyond_five_are_ignored():
    assert knowledge_capital([100.0] * 8) == 300.0


def test_no_rnd_history_is_nan_not_zero():
    """'Reports no R&D' and 'we could not find the row' are different facts.
    Collapsing them would rank hardware distributors and unparsed filings as
    the same thing."""
    assert np.isnan(knowledge_capital([]))
    assert np.isnan(knowledge_capital(None))
    assert np.isnan(knowledge_capital([100.0, float("nan")]))


def test_capitalising_rnd_makes_a_research_heavy_firm_look_cheaper():
    """The whole point: two firms with identical reported book equity and
    market cap, one of which spends heavily on research."""
    spender = adjusted_book_to_market([200.0] * 5, book_equity=100.0, market_cap=2000.0)
    miser = adjusted_book_to_market([0.0] * 5, book_equity=100.0, market_cap=2000.0)
    assert spender > miser
    # 100 reported + 600 knowledge capital, over a 2000 cap.
    assert spender == (100.0 + 600.0) / 2000.0
    assert miser == 100.0 / 2000.0


def test_missing_inputs_are_nan():
    assert np.isnan(adjusted_book_to_market([100.0], None, 2000.0))
    assert np.isnan(adjusted_book_to_market([100.0], 100.0, None))
    assert np.isnan(adjusted_book_to_market([100.0], 100.0, 0.0))      # cap <= 0
    assert np.isnan(adjusted_book_to_market(None, 100.0, 2000.0))


def test_negative_book_equity_still_scores():
    """Buyback-heavy tech often reports negative equity. Capitalised R&D can
    pull it back above zero, and that is a real change in the measure rather
    than a case to discard."""
    v = adjusted_book_to_market([500.0] * 5, book_equity=-200.0, market_cap=1000.0)
    assert v == (-200.0 + 1500.0) / 1000.0


def test_score_ranks_cheaper_adjusted_book_higher():
    metrics = pd.DataFrame(
        {
            "rnd_annual": [[300.0] * 5, [10.0] * 5, [100.0] * 5],
            "book_equity": [100.0, 100.0, 100.0],
        },
        index=["RESEARCHY", "ASSETLIGHT", "MIDDLE"],
    )
    caps = pd.Series(
        {"RESEARCHY": 2000.0, "ASSETLIGHT": 2000.0, "MIDDLE": 2000.0}
    )
    s = score(metrics, caps)
    assert s["RESEARCHY"] > s["MIDDLE"] > s["ASSETLIGHT"]
    assert s.between(0, 100).all()


def test_score_is_nan_when_nothing_is_parseable():
    """Column still emitted — composite_score gives an unlisted category
    weight 0.0 and the report skips a near-constant column rather than
    manufacturing a highlight."""
    metrics = pd.DataFrame(
        {"rnd_annual": [[], []], "book_equity": [100.0, 100.0]},
        index=["A", "B"],
    )
    s = score(metrics, pd.Series({"A": 1000.0, "B": 1000.0}))
    assert s.isna().all()
    assert list(s.index) == ["A", "B"]
