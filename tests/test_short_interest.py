"""Short-interest signal: heavily/increasingly shorted names rank low."""

import numpy as np
import pandas as pd

from stock_selector.signals import short_interest


def _frame(rows: dict[str, tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            t: {
                "shortPercentOfFloat": pf,
                "sharesShort": s,
                "sharesShortPriorMonth": p,
            }
            for t, (pf, s, p) in rows.items()
        }
    ).T


def test_lightly_shorted_beats_heavily_shorted():
    scores = short_interest.score(_frame({
        "LIGHT": (0.01, 1_000_000, 1_100_000),   # low and falling
        "MID": (0.08, 5_000_000, 5_000_000),
        "HEAVY": (0.30, 20_000_000, 12_000_000),  # high and piling in
    }))
    assert scores["LIGHT"] > scores["MID"] > scores["HEAVY"]


def test_rising_shorts_rank_below_falling_at_same_level():
    scores = short_interest.score(_frame({
        "FALLING": (0.10, 4_000_000, 6_000_000),
        "RISING": (0.10, 6_000_000, 4_000_000),
    }))
    assert scores["FALLING"] > scores["RISING"]


def test_missing_short_data_stays_nan():
    scores = short_interest.score(_frame({
        "A": (0.05, 2_000_000, 2_000_000),
        "B": (0.15, 8_000_000, 7_000_000),
        "NODATA": (None, None, None),
    }))
    assert np.isnan(scores["NODATA"])
    assert scores["A"] > scores["B"]
