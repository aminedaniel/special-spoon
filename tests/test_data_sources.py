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


def test_form4_parse_nets_open_market_only():
    # P buy $10,500 - S sale $2,000; the A award row is ignored.
    client = _client_with_map({"S": 1583708})
    buy, sell = client._parse_form4(FORM4_XML)
    assert buy == 10500.0
    assert sell == 2000.0


def test_edgar_activity_scoped_to_issuer_submissions():
    # Single-letter ticker 'S' must read the issuer's own submissions feed,
    # not text matches across all of EDGAR.
    client = _client_with_map({"S": 1583708})
    recent_date = (date.today() - timedelta(days=3)).isoformat()
    old_date = (date.today() - timedelta(days=90)).isoformat()
    submissions = {
        "filings": {
            "recent": {
                "form": ["4", "10-Q", "4", "4"],
                "filingDate": [recent_date, recent_date, recent_date, old_date],
                "accessionNumber": ["0001-24-001", "0001-24-002", "0001-24-003", "0001-24-004"],
                "primaryDocument": ["form4.xml", "10q.htm", "form4b.xml", "form4c.xml"],
            }
        }
    }

    class FakeResp:
        text = FORM4_XML
        def raise_for_status(self):
            pass

    with patch.object(client, "_get_json", return_value=submissions), patch.object(
        client.session, "get", return_value=FakeResp()
    ), patch("stock_selector.data_sources.sec_insider.time.sleep"):
        out = client.recent_form4_activity("S")
    # two in-window Form 4s, each netting +$8,500
    assert out == {"net_dollars": 17000.0, "filings": 2}


def test_edgar_unknown_ticker_returns_none():
    client = _client_with_map({})
    assert client.recent_form4_activity("NOPE") is None
