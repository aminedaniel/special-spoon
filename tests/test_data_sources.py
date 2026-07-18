"""Data-source behavior: congress staleness detection, EDGAR CIK resolution."""

from datetime import date, timedelta
from unittest.mock import patch

from stock_selector.data_sources import congress_trades, sec_insider

RECENT = (date.today() - timedelta(days=5)).strftime("%m/%d/%Y")
STALE = "01/15/2020"


@patch("stock_selector.data_sources.congress_trades._fetch")
def test_congress_counts_recent_transactions(mock_fetch):
    mock_fetch.return_value = [
        {"ticker": "AAAA", "transaction_date": RECENT, "type": "purchase"},
        {"ticker": "AAAA", "transaction_date": RECENT, "type": "sale (full)"},
        {"ticker": "ZZZZ", "transaction_date": RECENT, "type": "purchase"},
    ]
    out = congress_trades.fetch_recent_activity(["AAAA", "BBBB"])
    assert out == {"AAAA": {"buys": 2, "sells": 2}, "BBBB": {"buys": 0, "sells": 0}}


@patch("stock_selector.data_sources.congress_trades._fetch")
def test_congress_stale_feed_returns_none(mock_fetch):
    # Feed reachable but every transaction predates the window (dead dataset):
    # must be None (no information), not zeros for everyone.
    mock_fetch.return_value = [
        {"ticker": "AAAA", "transaction_date": STALE, "type": "purchase"},
    ]
    assert congress_trades.fetch_recent_activity(["AAAA"]) is None


@patch("stock_selector.data_sources.congress_trades._fetch")
def test_congress_all_feeds_down_returns_none(mock_fetch):
    mock_fetch.side_effect = ConnectionError("boom")
    assert congress_trades.fetch_recent_activity(["AAAA"]) is None


def _client_with_map(cik_map):
    client = sec_insider.EdgarClient("test-suite test@example.com")
    client._cik_map = cik_map
    return client


def test_edgar_counts_only_issuer_form4s():
    # Single-letter ticker 'S' must count the issuer's own Form 4s from its
    # submissions feed, not text matches across all of EDGAR.
    client = _client_with_map({"S": 1583708})
    recent_date = (date.today() - timedelta(days=3)).isoformat()
    old_date = (date.today() - timedelta(days=90)).isoformat()
    submissions = {
        "filings": {
            "recent": {
                "form": ["4", "10-Q", "4", "4"],
                "filingDate": [recent_date, recent_date, recent_date, old_date],
            }
        }
    }
    with patch.object(client, "_get_json", return_value=submissions):
        assert client.recent_form4_count("S") == 2  # two in-window Form 4s


def test_edgar_unknown_ticker_returns_none():
    client = _client_with_map({})
    assert client.recent_form4_count("NOPE") is None
