"""Scoreboard grading math and rendering on synthetic prices."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from stock_selector.scoreboard import (
    IC_HORIZON_DAYS,
    fixed_horizon_return,
    grade,
    render_markdown,
    window_return,
)


def _closes():
    idx = pd.bdate_range("2026-06-01", "2026-06-30")
    n = len(idx)
    # AAAA doubles linearly, BBBB flat, QQQ +10%, IWM -10% over the window
    return pd.DataFrame(
        {
            "AAAA": np.linspace(100, 200, n),
            "BBBB": np.full(n, 50.0),
            "QQQ": np.linspace(100, 110, n),
            "IWM": np.linspace(100, 90, n),
        },
        index=idx,
    )


def test_window_return_from_report_date():
    closes = _closes()
    ret = window_return(closes["QQQ"], date(2026, 6, 1))
    assert ret == pytest.approx(0.10)


def _long_closes():
    """120 calendar days of steady compounding, so a fixed window has a known
    length regardless of which start date is used."""
    idx = pd.date_range("2026-01-05", periods=120, freq="D")
    return pd.Series([100.0 * (1.001 ** i) for i in range(120)], index=idx)


def test_fixed_horizon_window_is_equal_length_where_to_date_is_not():
    """The whole point of the change. Two reports a week apart get windows of
    DIFFERENT length under window_return (both end at the last close) but the
    SAME length under fixed_horizon_return — so only the latter can be averaged
    across reports."""
    c = _long_closes()
    early, late = date(2026, 1, 5), date(2026, 1, 12)

    assert window_return(c, early) != pytest.approx(window_return(c, late))
    assert fixed_horizon_return(c, early) == pytest.approx(
        fixed_horizon_return(c, late), rel=1e-6
    )


def test_fixed_horizon_returns_none_before_the_window_closes():
    """A report too recent to have a full horizon must be skipped, not graded
    over a short window — a partial window is a different measurement, not a
    smaller sample."""
    c = _long_closes()
    start = date(2026, 1, 5)
    truncated = c[c.index.date <= start + timedelta(days=10)]
    assert fixed_horizon_return(truncated, start) is None
    # Exactly reaching the horizon is enough.
    exact = c[c.index.date <= start + timedelta(days=IC_HORIZON_DAYS)]
    assert fixed_horizon_return(exact, start) is not None


def test_fixed_horizon_handles_a_ticker_with_no_prices():
    """The realistic empty case: a ticker present in the panel but with no
    usable closes. dropna() leaves an empty series that still carries the
    panel's DatetimeIndex, which is what the function must survive."""
    empty = pd.Series(dtype="float64", index=pd.DatetimeIndex([]))
    assert fixed_horizon_return(empty, date(2026, 1, 5)) is None
    # All-NaN for a real date range reduces to the same case.
    all_nan = pd.Series(
        [np.nan] * 5, index=pd.date_range("2026-01-05", periods=5, freq="D")
    )
    assert fixed_horizon_return(all_nan, date(2026, 1, 5)) is None


def test_grade_computes_alpha_and_hit_rate():
    closes = _closes()
    d = date(2026, 6, 1)
    out = grade([d], {d: ["AAAA", "BBBB"]}, closes)
    row = out.iloc[0]
    assert row["picks_graded"] == 2
    assert row["avg_pick_return"] == pytest.approx((1.0 + 0.0) / 2)
    assert row["alpha_vs_qqq"] == pytest.approx(0.5 - 0.10)
    assert row["hit_rate_vs_qqq"] == pytest.approx(0.5)  # AAAA beats QQQ, BBBB doesn't


def test_grade_skips_unpriced_report():
    closes = _closes()
    d = date(2026, 6, 1)
    out = grade([d], {d: ["ZZZZ"]}, closes)  # ticker absent from price data
    assert out.empty


def test_render_markdown_empty_and_filled():
    empty = render_markdown(pd.DataFrame(), date(2026, 7, 17))
    assert "No reports old enough" in empty

    closes = _closes()
    d = date(2026, 6, 1)
    filled = render_markdown(grade([d], {d: ["AAAA"]}, closes), date(2026, 7, 17))
    assert "2026-06-01" in filled
    assert "Alpha vs QQQ" in filled
