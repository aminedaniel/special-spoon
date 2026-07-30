"""PEAD earnings-surprise extraction and drift-window behavior."""

from datetime import date

import numpy as np
import pandas as pd

from stock_selector.data_sources.earnings import (
    DRIFT_WINDOW_DAYS,
    surprise_asof,
    standardized_surprise,
)
from stock_selector.signals import earnings_drift

AS_OF = date(2026, 7, 29)


def _frame(rows: dict[str, tuple[float | None, float | None]]) -> pd.DataFrame:
    """rows: {iso_date: (estimate, reported)} in yfinance earnings_dates shape."""
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in rows])
    return pd.DataFrame(
        {
            "EPS Estimate": [v[0] for v in rows.values()],
            "Reported EPS": [v[1] for v in rows.values()],
        },
        index=idx,
    )


def test_latest_in_window_picks_newest_reported():
    f = _frame({
        "2026-01-20": (0.50, 0.55),
        "2026-07-15": (0.60, 0.72),          # 14 days before as_of — in window
        "2026-10-20": (0.65, None),          # scheduled future date
    })
    out = surprise_asof(f, AS_OF)
    assert out is not None
    assert out["days_since"] == 14
    assert out["surprise_pct"] == (0.72 - 0.60) / 0.60 * 100.0


def test_announcement_past_drift_window_is_none():
    stale = AS_OF - pd.Timedelta(days=DRIFT_WINDOW_DAYS + 1)
    f = _frame({stale.isoformat(): (0.50, 0.90)})
    assert surprise_asof(f, AS_OF) is None


def test_missing_estimate_is_none():
    f = _frame({"2026-07-15": (None, 0.72)})
    assert surprise_asof(f, AS_OF) is None


def test_sue_scales_by_prior_volatility():
    # Same +5% beat: the steady company scores far higher than the wild one.
    steady = standardized_surprise([1.0, -1.0, 0.5, -0.5], 5.0)
    wild = standardized_surprise([20.0, -18.0, 25.0, -22.0], 5.0)
    assert steady > wild
    # Too few priors -> raw surprise, unscaled.
    assert standardized_surprise([1.0], 5.0) == 5.0


def test_signal_ranks_beats_above_misses_with_nan_for_no_info():
    scores = earnings_drift.score({
        "BEAT": {"sue": 3.0, "surprise_pct": 12.0, "days_since": 10},
        "MISS": {"sue": -2.0, "surprise_pct": -8.0, "days_since": 20},
        "NONE": None,
    })
    assert scores["BEAT"] > scores["MISS"]
    assert np.isnan(scores["NONE"])


def test_duplicate_announcement_timestamps_collapse():
    """Some issuers return duplicate rows for one announcement (restatements,
    dual listings). Without collapsing, .loc[ts] yields a Series and the
    arithmetic raises — which would abort a whole run on one bad ticker."""
    f = pd.DataFrame(
        {"EPS Estimate": [0.60, 0.60], "Reported EPS": [0.70, 0.72]},
        index=pd.DatetimeIndex(["2026-07-15", "2026-07-15"]),
    )
    out = surprise_asof(f, AS_OF)
    assert out is not None
    # keep="last" wins
    assert out["surprise_pct"] == (0.72 - 0.60) / 0.60 * 100.0


def test_tz_aware_index_is_accepted():
    f = pd.DataFrame(
        {"EPS Estimate": [0.60], "Reported EPS": [0.72]},
        index=pd.DatetimeIndex(["2026-07-15"], tz="America/New_York"),
    )
    assert surprise_asof(f, AS_OF) is not None


def test_unparseable_index_returns_none_not_raises():
    f = pd.DataFrame(
        {"EPS Estimate": [0.60], "Reported EPS": [0.72]}, index=["not-a-date"]
    )
    assert surprise_asof(f, AS_OF) is None
