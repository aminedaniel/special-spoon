"""Recommendation tracker: ledger anchoring, deferral, and render math."""

from datetime import date

import pandas as pd
import pytest

from stock_selector.tracker import (
    DEFAULT_TOP_N,
    LEDGER_COLUMNS,
    add_new_picks,
    backfill_from_reports,
    render_markdown,
    top_picks,
)


def test_default_tracks_only_top_pick(tmp_path):
    csv = tmp_path / "rankings_2026-07-28.csv"
    pd.DataFrame({"ticker": ["AAAA", "BBBB", "CCCC"], "rank": [1, 2, 3]}).to_csv(
        csv, index=False
    )
    assert DEFAULT_TOP_N == 1
    assert top_picks(csv, top_n=DEFAULT_TOP_N) == ["AAAA"]


def _empty_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=LEDGER_COLUMNS)


def test_top_picks_respects_rank(tmp_path):
    csv = tmp_path / "rankings_2026-07-28.csv"
    pd.DataFrame(
        {"ticker": ["CCCC", "AAAA", "BBBB"], "rank": [3, 1, 2]}
    ).to_csv(csv, index=False)
    assert top_picks(csv, top_n=2) == ["AAAA", "BBBB"]


def test_add_new_picks_sets_anchor():
    ledger = add_new_picks(
        _empty_ledger(), ["AAAA", "BBBB"], date(2026, 7, 20),
        {"AAAA": 100.0, "BBBB": 50.0},
    )
    assert set(ledger["ticker"]) == {"AAAA", "BBBB"}
    row = ledger[ledger["ticker"] == "AAAA"].iloc[0]
    assert row["first_recommended"] == "2026-07-20"
    assert row["first_price"] == 100.0


def test_existing_anchor_never_resets():
    # AAAA already tracked from an earlier date/price; re-recommending it later
    # must NOT change its anchor.
    ledger = add_new_picks(
        _empty_ledger(), ["AAAA"], date(2026, 7, 20), {"AAAA": 100.0}
    )
    ledger = add_new_picks(
        ledger, ["AAAA", "BBBB"], date(2026, 7, 27),
        {"AAAA": 130.0, "BBBB": 40.0},
    )
    aaaa = ledger[ledger["ticker"] == "AAAA"]
    assert len(aaaa) == 1  # not duplicated
    assert aaaa.iloc[0]["first_recommended"] == "2026-07-20"  # unchanged
    assert aaaa.iloc[0]["first_price"] == 100.0               # unchanged
    assert "BBBB" in set(ledger["ticker"])                    # new one added


def test_pick_without_price_is_deferred():
    ledger = add_new_picks(
        _empty_ledger(), ["AAAA", "BBBB"], date(2026, 7, 20),
        {"AAAA": 100.0, "BBBB": None},
    )
    assert set(ledger["ticker"]) == {"AAAA"}  # BBBB skipped, tries again next run


def test_render_computes_change_and_days():
    ledger = pd.DataFrame(
        {
            "ticker": ["AAAA"],
            "first_recommended": ["2026-07-20"],
            "first_price": [100.0],
        }
    )
    md = render_markdown(ledger, {"AAAA": 125.0}, date(2026, 7, 28))
    assert "+25.0%" in md
    assert "| 8 |" in md          # 8 days held
    assert "$100.00" in md and "$125.00" in md


def test_render_handles_missing_current_price():
    ledger = pd.DataFrame(
        {"ticker": ["AAAA"], "first_recommended": ["2026-07-20"], "first_price": [100.0]}
    )
    md = render_markdown(ledger, {"AAAA": None}, date(2026, 7, 28))
    assert "—" in md  # no current price -> dash, no crash


def test_render_empty_ledger():
    md = render_markdown(pd.DataFrame(columns=LEDGER_COLUMNS), {}, date(2026, 7, 28))
    assert "No recommendations tracked yet" in md


def test_backfill_anchors_earliest_date(tmp_path):
    # Two weekly reports; a ticker in both must anchor to the OLDER date.
    pd.DataFrame({"ticker": ["QLYS", "DBX"], "rank": [1, 2]}).to_csv(
        tmp_path / "rankings_2026-07-20.csv", index=False
    )
    pd.DataFrame({"ticker": ["RNG", "DBX"], "rank": [1, 2]}).to_csv(
        tmp_path / "rankings_2026-07-27.csv", index=False
    )

    prices = {
        ("QLYS", date(2026, 7, 20)): 140.0,
        ("DBX", date(2026, 7, 20)): 27.0,
        ("RNG", date(2026, 7, 27)): 40.0,
        ("DBX", date(2026, 7, 27)): 30.0,  # must be ignored — DBX already anchored
    }

    def close_on(ticker, on):
        return prices.get((ticker, on))

    ledger = backfill_from_reports(
        pd.DataFrame(columns=LEDGER_COLUMNS), tmp_path, close_on, top_n=2
    )
    assert set(ledger["ticker"]) == {"QLYS", "DBX", "RNG"}
    dbx = ledger[ledger["ticker"] == "DBX"].iloc[0]
    assert dbx["first_recommended"] == "2026-07-20"  # earliest wins
    assert dbx["first_price"] == 27.0
