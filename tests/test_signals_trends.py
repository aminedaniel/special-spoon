"""Google Trends momentum computation and scoring."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from stock_selector.data_sources import google_trends
from stock_selector.data_sources.google_trends import (
    fetch_interest_momentum,
    interest_momentum,
)
from stock_selector.signals.trends import score


def test_momentum_positive_when_recent_elevated():
    # 90 days flat at 10, last 14 days jump to 30 -> strong positive momentum
    series = pd.Series([10.0] * 76 + [30.0] * 14)
    m = interest_momentum(series)
    assert m == pytest.approx(30.0 / 10.0 - 1.0)


def test_momentum_negative_when_recent_cools():
    series = pd.Series([20.0] * 76 + [10.0] * 14)
    assert interest_momentum(series) < 0


def test_momentum_none_on_short_series():
    assert interest_momentum(pd.Series([1.0, 2.0, 3.0])) is None


def test_momentum_none_on_zero_baseline():
    # No historical interest -> ratio undefined -> None (not inf)
    series = pd.Series([0.0] * 76 + [50.0] * 14)
    assert interest_momentum(series) is None


def test_score_ranks_higher_momentum_first():
    s = score({"HOT": 1.5, "WARM": 0.2, "COLD": -0.3})
    assert s["HOT"] > s["WARM"] > s["COLD"]
    assert s.between(0, 100).all()


def test_score_keeps_none_as_nan():
    s = score({"A": 0.5, "B": None})
    assert np.isnan(s["B"])


def test_fetch_drops_partial_final_bucket():
    # Baseline flat at 10, recent flat at 20, plus a spurious 100 in the still-
    # open final bucket flagged isPartial=True. Dropping it must yield the clean
    # 20/10-1 momentum; keeping it would inflate the recent-window mean.
    kw = "AAAA stock"
    idx = pd.date_range("2026-04-01", periods=91, freq="D")
    values = [10.0] * 76 + [20.0] * 14 + [100.0]
    partial = [False] * 90 + [True]
    frame = pd.DataFrame({kw: values, "isPartial": partial}, index=idx)

    class FakeTrendReq:
        def __init__(self, *a, **k):
            pass

        def build_payload(self, *a, **k):
            pass

        def interest_over_time(self):
            return frame

    with patch.object(google_trends, "time"), patch(
        "pytrends.request.TrendReq", FakeTrendReq
    ):
        out = fetch_interest_momentum(["AAAA"])
    assert out["AAAA"] == pytest.approx(20.0 / 10.0 - 1.0)
