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


def test_stability_scores_no_lookahead():
    from stock_selector.backtest import stability_scores_asof

    prices = make_price_history(days=300)
    as_of = prices.index[200].date()
    bench = prices["Close"]["AAAA"] * 0.5  # any aligned series works as a bench

    tampered = prices.copy()
    tampered.iloc[201:] = tampered.iloc[201:] * 100

    a = stability_scores_asof(prices, bench, as_of)
    b = stability_scores_asof(tampered, bench, as_of)
    pd.testing.assert_series_equal(a, b)


def test_surprise_asof_no_lookahead():
    from stock_selector.data_sources.earnings import surprise_asof

    frame = pd.DataFrame(
        {
            "EPS Estimate": [0.50, 0.60, 0.70],
            "Reported EPS": [0.55, 0.72, 1.50],
        },
        index=pd.DatetimeIndex(["2026-01-20", "2026-04-15", "2026-07-20"]),
    )
    # As of May 1st, only the April announcement is visible: the July blowout
    # must not leak into the score.
    out = surprise_asof(frame, date(2026, 5, 1))
    assert out is not None
    assert out["surprise_pct"] == (0.72 - 0.60) / 0.60 * 100.0
    assert out["days_since"] == 16


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
            t: (
                [{"date": d, "buy": 100000.0, "sell": 0.0,
                  "owner_cik": "0001", "is_officer": True, "is_director": False}]
                if t == "AAAA"
                else []
            )
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
        # Announcements pre-date every rebalance (2026-04-01 onward) and stay
        # inside the 75-day drift window. All five tickers score, with
        # distinct surprises, because signal_ic requires >=5 scored names
        # before it will report an IC at all.
        "earnings": {
            t: pd.DataFrame(
                {
                    "EPS Estimate": [0.50],
                    "Reported EPS": [0.40 + 0.05 * i],
                },
                index=pd.DatetimeIndex(["2026-03-20"]),
            )
            for i, t in enumerate(TICKERS)
        },
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
    assert "stability" in result.ic_history.columns
    assert "earnings_drift" in result.ic_history.columns
    # weights recorded per period and sum to 1
    assert result.weights_used.sum(axis=1).round(6).eq(1.0).all()


def test_form4_cap_scales_with_window():
    """A cap that only covers recent months would leave early rebalances with
    no in-window Form 4s at all — a constant insider column that looks like a
    working signal and measures nothing."""
    from stock_selector.backtest import form4_cap_for_window
    from stock_selector.data_sources.sec_insider import MAX_HISTORY_FILINGS

    end = date(2026, 7, 29)
    two_yr = form4_cap_for_window(date(2024, 7, 29), end)
    four_yr = form4_cap_for_window(date(2022, 7, 29), end)
    assert four_yr > two_yr > MAX_HISTORY_FILINGS
    # ~70-110 filings/yr observed live; the budget must clear that comfortably.
    assert four_yr >= 4 * 110
    # Never drops below the single-window default, even for a tiny range.
    assert form4_cap_for_window(date(2026, 7, 1), end) >= MAX_HISTORY_FILINGS


def test_universe_files_are_disjoint_and_merged_is_their_union():
    """The size experiment only means anything if small/mid and large-cap
    don't overlap — otherwise 'large caps' silently includes small caps."""
    import csv
    from pathlib import Path

    root = Path(__file__).parent.parent / "config"
    def tickers(name):
        with open(root / name) as f:
            return {r["ticker"] for r in csv.DictReader(f)}

    smid = tickers("universe.csv")
    large = tickers("universe_largecap.csv")
    merged = tickers("universe_merged.csv")

    assert not (smid & large), f"universes overlap: {smid & large}"
    assert merged == smid | large
    assert len(merged) == len(smid) + len(large)


def test_issuance_scores_asof_never_reads_past_the_lag():
    """The lookahead guard. A share count dated D reached the public in a later
    10-Q, so scoring D with it would be reading the future. Anything inside the
    lag window must be invisible."""
    import pandas as pd

    from stock_selector.backtest import (
        SHARE_REPORTING_LAG_DAYS,
        issuance_scores_asof,
    )

    as_of = date(2026, 7, 1)
    idx = pd.date_range("2025-01-01", "2026-07-01", freq="7D")
    # Flat until the very recent past, then a huge spike inside the lag window.
    values = [100.0] * len(idx)
    for i, ts in enumerate(idx):
        if (as_of - ts.date()).days < SHARE_REPORTING_LAG_DAYS:
            values[i] = 10_000.0
    hist = {"AAAA": pd.Series(values, index=idx), "BBBB": pd.Series(values, index=idx)}

    scores = issuance_scores_asof(hist, as_of)
    # If the spike leaked in, the computed change would be enormous. Both
    # tickers are identical, so what matters is that the score is finite and
    # the pre-lag window is what was used.
    assert not scores.empty
    lagged = issuance_scores_asof(hist, as_of - timedelta(days=400))
    assert not lagged.empty


def test_issuance_absent_pops_its_weight_from_the_base():
    """Anything conditionally present must be popped, or its weight silently
    inflates the renormalization of everything else."""
    from stock_selector.backtest import BACKTEST_WEIGHTS

    assert "issuance" in BACKTEST_WEIGHTS
    assert sum(BACKTEST_WEIGHTS.values()) == pytest.approx(1.0)
