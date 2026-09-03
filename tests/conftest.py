"""Shared synthetic fixtures: deterministic price history and fundamentals."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

TICKERS = ["AAAA", "BBBB", "CCCC", "DDDD", "EEEE"]


def make_price_history(tickers: list[str] = TICKERS, days: int = 300) -> pd.DataFrame:
    """yfinance-shaped (field, ticker) frame with distinct per-ticker trends."""
    rng = np.random.default_rng(42)
    idx = pd.bdate_range(end="2026-07-17", periods=days)
    frames = {}
    # Per-ticker daily drift: AAAA strong uptrend ... EEEE downtrend.
    drifts = np.linspace(0.002, -0.002, num=len(tickers))
    for ticker, drift in zip(tickers, drifts):
        returns = rng.normal(loc=drift, scale=0.01, size=days)
        close = 100 * np.exp(np.cumsum(returns))
        frames[("Close", ticker)] = close
        frames[("Volume", ticker)] = rng.integers(1e5, 5e5, size=days).astype(float)
    df = pd.DataFrame(frames, index=idx)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


def make_fundamentals(tickers: list[str] = TICKERS) -> pd.DataFrame:
    rows = {
        t: {
            "marketCap": cap,
            "trailingPE": pe,
            "forwardPE": pe,
            "revenueGrowth": growth,
            "debtToEquity": dte,
            "dividendYield": 0.0,
            "returnOnEquity": roe,
            "grossMargins": 0.6,
            # Per-ticker accrual gap. These were both flat multiples of cap,
            # so (ocf - ni)/cap was exactly 0.02 for every ticker — a constant
            # column that could not rank anything. Dilution used to mask it
            # inside `quality`; once issuance was split out the degenerate
            # guard caught it immediately.
            "operatingCashflow": cap * ocf_r,
            "netIncomeToCommon": cap * ni_r,
            "priceToSalesTrailing12Months": ps,
            "enterpriseToRevenue": ps * 0.95,
            "enterpriseToEbitda": ps * 4,
            "pegRatio": peg,
            "freeCashflow": cap * 0.04,
            "sharesShort": short_now,
            "sharesShortPriorMonth": short_prior,
            "shortPercentOfFloat": short_pct,
            "sector": "Technology",
            "shortName": f"{t} Corp",
        }
        for (
            t, cap, pe, growth, dte, roe, ps, peg,
            short_pct, short_now, short_prior, ocf_r, ni_r,
        ) in [
            # ocf_r / ni_r give each ticker a distinct accrual gap:
            # AAAA +3.0%, BBBB +1.5%, CCCC +0.5%, DDDD -0.5%, EEEE +2.0%
            ("AAAA", 2e9, 25.0, 0.40, 20.0, 0.25, 4.0, 1.2, 0.02, 1e6, 1.2e6, 0.060, 0.030),
            ("BBBB", 5e9, 35.0, 0.25, 50.0, 0.15, 8.0, 2.0, 0.06, 3e6, 2.8e6, 0.050, 0.035),
            ("CCCC", 8e8, None, 0.60, 10.0, -0.05, 3.0, 1.0, 0.12, 5e6, 4e6, 0.015, 0.010),   # unprofitable grower
            ("DDDD", 9e9, 55.0, 0.10, 120.0, 0.10, 12.0, 3.5, 0.25, 9e6, 5e6, 0.020, 0.025),  # paper earnings
            ("EEEE", 4e8, 12.0, -0.05, 80.0, 0.08, 1.5, None, None, None, None, 0.040, 0.020),  # cheap, no PEG/short data
        ]
    }
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "ticker"
    return df


@pytest.fixture
def price_history() -> pd.DataFrame:
    return make_price_history()


@pytest.fixture
def fundamentals() -> pd.DataFrame:
    return make_fundamentals()
