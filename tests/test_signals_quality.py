"""Quality signal: accrual gap and dilution direction."""

import pandas as pd

from stock_selector.signals.quality import score


def test_cash_backed_earnings_beat_paper_earnings():
    f = pd.DataFrame(
        {
            "marketCap": [1e9, 1e9],
            "operatingCashflow": [100e6, 0.0],
            "netIncomeToCommon": [50e6, 50e6],  # same earnings, different cash
        },
        index=["CASH", "PAPER"],
    )
    s = score(f)
    assert s["CASH"] > s["PAPER"]


def test_dilution_penalized():
    f = pd.DataFrame(
        {
            "marketCap": [1e9, 1e9],
            "operatingCashflow": [50e6, 50e6],
            "netIncomeToCommon": [40e6, 40e6],
        },
        index=["BUYBACK", "DILUTER"],
    )
    share_change = pd.Series({"BUYBACK": -0.03, "DILUTER": 0.10})
    s = score(f, share_change)
    assert s["BUYBACK"] > s["DILUTER"]
