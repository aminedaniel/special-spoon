"""Scoreboard grading math and rendering on synthetic prices."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from stock_selector.scoreboard import grade, render_markdown, window_return


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
