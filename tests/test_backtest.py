"""Backtest engine: date math, forward returns, no-lookahead, full loop."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from stock_selector.backtest import (
    rebalance_dates,
    run_backtest,
    technical_scores_asof,
    window_forward_return,
)

from conftest import TICKERS, make_price_history


def test_rebalance_dates_step_and_bounds():
    dates = rebalance_dates(date(2026, 1, 5), date(2026, 3, 30), step_weeks=4)
    assert dates == [date(2026, 1, 5), date(2026, 2, 2), date(2026, 3, 2)]


def test_window_forward_return():
    idx = pd.bdate_range("2026-01-01", periods=60)
    closes = pd.Series(np.linspace(100, 159, 60), index=idx)
    ret = window_forward_return(closes, date(2026, 1, 1), date(2026, 1, 15))
    entry = closes[closes.index.date >= date(2026, 1, 1)].iloc[0]
    exit_ = closes[closes.index.date >= date(2026, 1, 15)].iloc[0]
    assert ret == pytest.approx(float(exit_ / entry - 1))


def test_technical_scores_no_lookahead():
    prices = make_price_history(days=300)
    as_of = prices.index[200].date()

    tampered = prices.copy()
    # nuke everything after as_of; scores as-of that date must not change
    tampered.iloc[201:] = tampered.iloc[201:] * 100

    a = technical_scores_asof(prices, as_of)
    b = technical_scores_asof(tampered, as_of)
    pd.testing.assert_series_equal(a, b)


def _histories():
    d = date(2026, 6, 20)
    return {
        "form4": {
            t: ([(d, 100000.0)] if t == "AAAA" else [])
            for t in TICKERS
        },
        "filings": {
            t: (
                [{"form": "SC 13D", "filingDate": "2026-06-01", "items": "",
                  "accessionNumber": "x", "primaryDocument": "d.htm"}]
                if t == "BBBB"
                else []
            )
            for t in TICKERS
        },
        "text_cache": None,
    }


def test_run_backtest_produces_periods_ic_and_picks():
    prices = make_price_history(days=300)  # ends 2026-07-17
    bench = pd.DataFrame(
        {
            "QQQ": np.linspace(100, 110, len(prices)),
            "IWM": np.linspace(100, 95, len(prices)),
        },
        index=prices.index,
    )
    result = run_backtest(
        universe=list(TICKERS),
        prices=prices,
        bench_closes=bench,
        histories=_histories(),
        start=date(2026, 4, 1),
        end=date(2026, 7, 10),
        step_weeks=4,
        top_n=3,
        adaptive_weights=True,
        include_filing_text=False,
    )
    assert not result.periods.empty
    assert set(result.periods.columns) >= {
        "rebalance", "picks", "avg_return", "qqq_return", "alpha_vs_qqq",
    }
    assert not result.picks.empty
    assert result.picks["forward_return"].notna().all()
    # ICs recorded for the point-in-time signals
    assert "technical" in result.ic_history.columns
    # weights recorded per period and sum to 1
    assert result.weights_used.sum(axis=1).round(6).eq(1.0).all()
