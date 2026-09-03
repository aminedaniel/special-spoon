"""Quality signal: the accrual gap. Dilution moved to signals/issuance."""

import pandas as pd
import pytest

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


def test_quality_no_longer_absorbs_share_data():
    """Dilution left this signal. Previously, when share data was missing for a
    ticker, combine_subscores(skipna=True) produced a full-strength
    accruals-only score the composite could not distinguish from a fully
    covered one. quality is now unambiguously one thing."""
    f = pd.DataFrame(
        {
            "marketCap": [1e9, 1e9],
            "operatingCashflow": [100e6, 0.0],
            "netIncomeToCommon": [50e6, 50e6],
        },
        index=["CASH", "PAPER"],
    )
    assert score(f).notna().all()
    with pytest.raises(TypeError):
        score(f, pd.Series({"CASH": -0.03, "PAPER": 0.10}))  # no longer accepted
