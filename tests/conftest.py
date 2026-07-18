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
            "operatingCashflow": cap * 0.05,
            "netIncomeToCommon": cap * 0.03,
            "sector": "Technology",
            "shortName": f"{t} Corp",
        }
        for t, cap, pe, growth, dte, roe in [
            ("AAAA", 2e9, 25.0, 0.40, 20.0, 0.25),
            ("BBBB", 5e9, 35.0, 0.25, 50.0, 0.15),
            ("CCCC", 8e8, None, 0.60, 10.0, -0.05),   # unprofitable grower
            ("DDDD", 9e9, 55.0, 0.10, 120.0, 0.10),
            ("EEEE", 4e8, 12.0, -0.05, 80.0, 0.08),
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
