"""Share-count history: split adjustment, robust endpoints, tz normalization."""

import pandas as pd
import pytest

from stock_selector.data_sources.market_data import (
    normalize_share_index,
    split_adjust,
)


def _change(values, k=1):
    import statistics
    adj = split_adjust(values)
    kk = min(k, len(adj) // 2) or 1
    return statistics.median(adj[-kk:]) / statistics.median(adj[:kk]) - 1


def test_forward_split_is_not_read_as_dilution():
    """The failure this exists to prevent: a 2:1 split doubles the raw count,
    which the old endpoint ratio scored as +100% dilution — the worst possible
    rank — for a company whose share count did not economically change."""
    assert _change([100, 100, 200, 200]) == pytest.approx(0.0)


def test_reverse_split_is_not_read_as_a_buyback():
    """And the mirror image, which ranked BEST."""
    assert _change([1000, 1000, 100, 100]) == pytest.approx(0.0)


def test_real_issuance_survives_split_adjustment():
    """Adjustment must not launder away genuine dilution."""
    assert _change([100, 102, 105, 110]) == pytest.approx(0.10)
    assert _change([100, 99, 97, 95]) == pytest.approx(-0.05)


def test_split_and_real_dilution_together():
    """2:1 split plus 10% genuine issuance must read as 10%, not 120%."""
    assert _change([100, 100, 200, 220]) == pytest.approx(0.10)


def test_consecutive_splits_compound_correctly():
    assert _change([10, 10, 20, 20, 60, 60]) == pytest.approx(0.0)


def test_ordinary_growth_is_not_mistaken_for_a_split():
    """A 5% quarter-over-quarter rise must not trip the split detector."""
    assert _change([100, 105, 110, 115]) == pytest.approx(0.15)


def test_normalize_share_index_mixes_tz_aware_and_naive():
    """Measured live: 38 of 40 tickers returned tz-aware (America/New_York)
    indexes and 2 returned naive. Comparing the two raises in pandas, and the
    backtest slices these by as-of date on every rebalance."""
    aware = pd.Series(
        [1.0, 2.0],
        index=pd.to_datetime(["2026-01-01", "2026-02-01"]).tz_localize("America/New_York"),
    )
    naive = pd.Series([3.0, 4.0], index=pd.to_datetime(["2026-01-01", "2026-02-01"]))

    a, b = normalize_share_index(aware), normalize_share_index(naive)
    assert a.index.tz is None and b.index.tz is None
    # Both must now be directly comparable against a plain date.
    assert (a.index[0].date() < pd.Timestamp("2026-01-15").date())
    assert len(a) == len(b) == 2


def test_normalize_share_index_sorts_dedupes_and_drops_bad_dates():
    s = pd.Series(
        [1.0, 9.0, 2.0, 3.0],
        index=pd.to_datetime(
            ["2026-02-01", "2026-02-01", "2026-01-01", None], errors="coerce"
        ),
    )
    out = normalize_share_index(s)
    assert list(out.index.strftime("%Y-%m-%d")) == ["2026-01-01", "2026-02-01"]
    assert out.iloc[-1] == 9.0        # duplicate keeps the last value
