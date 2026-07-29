"""Valuation signal: cheaper multiples rank higher; robust to nulls/negatives."""

import numpy as np
import pandas as pd

from stock_selector.signals.valuation import score


def test_cheaper_multiples_score_higher():
    f = pd.DataFrame(
        {
            "marketCap": [1e9, 1e9, 1e9],
            "trailingPE": [10.0, 30.0, 50.0],
            "priceToSalesTrailing12Months": [2.0, 6.0, 10.0],
            "enterpriseToRevenue": [2.0, 6.0, 10.0],
            "enterpriseToEbitda": [8.0, 15.0, 25.0],
            "pegRatio": [1.0, 2.0, 3.0],
            "freeCashflow": [1e8, 5e7, 2e7],  # P/FCF 10, 20, 50
        },
        index=["CHEAP", "MID", "RICH"],
    )
    s = score(f)
    assert s["CHEAP"] > s["MID"] > s["RICH"]
    assert s.between(0, 100).all()


def test_unprofitable_name_scored_on_sales_multiples():
    # No P/E and negative FCF, but P/S and EV/Sales still price it.
    f = pd.DataFrame(
        {
            "marketCap": [1e9, 1e9],
            "trailingPE": [np.nan, 20.0],
            "priceToSalesTrailing12Months": [2.0, 8.0],
            "enterpriseToRevenue": [2.0, 8.0],
            "enterpriseToEbitda": [np.nan, 15.0],
            "pegRatio": [np.nan, 2.0],
            "freeCashflow": [-5e7, 5e7],  # negative FCF -> no P/FCF signal
        },
        index=["GROWTH", "PROFITABLE"],
    )
    s = score(f)
    assert not np.isnan(s["GROWTH"])          # still scored on sales multiples
    assert s["GROWTH"] > s["PROFITABLE"]      # cheaper on P/S -> ranks higher


def test_negative_pe_gives_no_signal_but_no_crash():
    f = pd.DataFrame(
        {
            "marketCap": [1e9],
            "trailingPE": [-5.0],                      # negative -> ignored
            "priceToSalesTrailing12Months": [3.0],
            "enterpriseToRevenue": [np.nan],
            "enterpriseToEbitda": [np.nan],
            "pegRatio": [np.nan],
            "freeCashflow": [np.nan],
        },
        index=["LOSS"],
    )
    s = score(f)
    assert 0 <= s["LOSS"] <= 100  # scored on P/S alone, no crash
