"""Data-source behavior: congress staleness, EDGAR CIK scoping, Form 4 math."""

from datetime import date, timedelta
from unittest.mock import patch

from stock_selector.data_sources import congress_trades, sec_insider
from stock_selector.data_sources.edgar import EdgarClient

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


FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>10.50</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>200</value></transactionShares>
        <transactionPricePerShare><value>10.00</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>99999</value></transactionShares>
        <transactionPricePerShare><value>0</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""


def _client_with_map(cik_map) -> EdgarClient:
    client = EdgarClient("test-suite test@example.com")
    client._cik_map = cik_map
    return client


def test_form4_parse_nets_open_market_only():
    # P buy $10,500 and S sale $2,000; the A award row is ignored.
    buy, sell = sec_insider.parse_form4(FORM4_XML)
    assert buy == 10500.0
    assert sell == 2000.0


def test_form4_history_scoped_to_issuer_submissions():
    # Single-letter ticker 'S' must read the issuer's own submissions feed,
    # not text matches across all of EDGAR.
    client = _client_with_map({"S": 1583708})
    recent_date = (date.today() - timedelta(days=3)).isoformat()
    old_date = (date.today() - timedelta(days=90)).isoformat()
    rows = [
        {"form": "4", "filingDate": recent_date, "accessionNumber": "a1", "primaryDocument": "form4.xml", "items": ""},
        {"form": "10-Q", "filingDate": recent_date, "accessionNumber": "a2", "primaryDocument": "10q.htm", "items": ""},
        {"form": "4", "filingDate": recent_date, "accessionNumber": "a3", "primaryDocument": "form4b.xml", "items": ""},
        {"form": "4", "filingDate": old_date, "accessionNumber": "a4", "primaryDocument": "form4c.xml", "items": ""},
    ]
    since = date.today() - timedelta(days=14)
    with patch.object(client, "recent_filings", return_value=rows), patch.object(
        client, "filing_text", return_value=FORM4_XML
    ):
        history = sec_insider.fetch_form4_history(client, "S", since)
    # two in-window Form 4s, each netting +$8,500
    assert [net for _, net in history] == [8500.0, 8500.0]

    activity = sec_insider.window_activity(history, date.today(), 14)
    assert activity == {"net_dollars": 17000.0, "filings": 2}


def test_window_activity_none_stays_none():
    assert sec_insider.window_activity(None, date.today(), 14) is None


def test_edgar_unknown_ticker_returns_none():
    client = _client_with_map({})
    assert sec_insider.fetch_form4_history(client, "NOPE", date.today()) is None
