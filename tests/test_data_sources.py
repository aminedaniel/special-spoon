"""Data-source behavior: EDGAR CIK scoping and Form 4 math."""

from datetime import date, timedelta
from unittest.mock import patch

from stock_selector.data_sources import sec_insider
from stock_selector.data_sources.edgar import EdgarClient

FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>0001111111</rptOwnerCik></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>0</isDirector>
      <isOfficer>1</isOfficer>
      <officerTitle>Chief Executive Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
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


# Same filing, but flagged as executed under a Rule 10b5-1 plan. Live filings
# use both encodings ("1"/"0" and "true"/"false"); both are covered.
FORM4_PLANNED_XML = FORM4_XML.replace(
    "<ownershipDocument>", "<ownershipDocument>\n  <aff10b5One>1</aff10b5One>"
)
FORM4_PLANNED_XML_BOOL = FORM4_XML.replace(
    "<ownershipDocument>", "<ownershipDocument>\n  <aff10b5One>true</aff10b5One>"
)


def _client_with_map(cik_map) -> EdgarClient:
    client = EdgarClient("test-suite test@example.com")
    client._cik_map = cik_map
    return client


def test_form4_parse_nets_open_market_only():
    # P buy $10,500 and S sale $2,000; the A award row is ignored.
    rec = sec_insider.parse_form4(FORM4_XML)
    assert rec["buy"] == 10500.0
    assert rec["sell"] == 2000.0
    assert rec["owner_cik"] == "0001111111"
    assert rec["is_officer"] and not rec["is_director"]
    assert rec["is_planned"] is False   # no aff10b5One element at all


def test_form4_parse_reads_10b5_1_flag_in_both_encodings():
    """Live filings encode the checkbox as 1/0 and as true/false; 47% of real
    Form 4s carry it set, so misreading it would silently discard half the
    exclusions."""
    assert sec_insider.parse_form4(FORM4_PLANNED_XML)["is_planned"] is True
    assert sec_insider.parse_form4(FORM4_PLANNED_XML_BOOL)["is_planned"] is True


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
    # two in-window Form 4s, each buy $10,500 / sell $2,000
    assert [r["buy"] - r["sell"] for r in history] == [8500.0, 8500.0]

    activity = sec_insider.window_activity(history, date.today(), 14)
    assert activity["filings"] == 2
    assert activity["net_dollars"] == 17000.0
    # Both filings are the same officer: weighted buys 2 * 10500 * 2.0,
    # one distinct buyer so no cluster multiplier, sells discounted 0.25.
    assert activity["signal_dollars"] == 2 * 10500.0 * 2.0 - 0.25 * 4000.0
    assert activity["distinct_buyers"] == 1


def test_window_activity_none_stays_none():
    assert sec_insider.window_activity(None, date.today(), 14) is None


def test_edgar_unknown_ticker_returns_none():
    client = _client_with_map({})
    assert sec_insider.fetch_form4_history(client, "NOPE", date.today()) is None


def test_cluster_of_distinct_buyers_outscores_one_whale():
    """Three insiders buying $10k each must outrank one insider buying $30k —
    the cluster configuration is the strongest signal in the literature."""
    today = date.today()
    def rec(cik, buy):
        return {"date": today, "buy": buy, "sell": 0.0,
                "owner_cik": cik, "is_officer": False, "is_director": True}
    cluster = sec_insider.window_activity(
        [rec("a", 10000.0), rec("b", 10000.0), rec("c", 10000.0)], today, 14
    )
    whale = sec_insider.window_activity([rec("a", 30000.0)], today, 14)
    assert cluster["signal_dollars"] > whale["signal_dollars"]
    assert cluster["net_dollars"] == whale["net_dollars"] == 30000.0


def test_officer_buy_outweighs_director_buy():
    today = date.today()
    officer = sec_insider.window_activity(
        [{"date": today, "buy": 10000.0, "sell": 0.0,
          "owner_cik": "x", "is_officer": True, "is_director": False}], today, 14
    )
    director = sec_insider.window_activity(
        [{"date": today, "buy": 10000.0, "sell": 0.0,
          "owner_cik": "x", "is_officer": False, "is_director": True}], today, 14
    )
    assert officer["signal_dollars"] == 2 * director["signal_dollars"]


def test_planned_buy_excluded_from_score_but_kept_in_raw_totals():
    """Cohen/Malloy/Pomorski: scheduled trades carry no information. A 10b5-1
    buy must not score, but must still reconcile against EDGAR."""
    today = date.today()
    planned = sec_insider.window_activity(
        [{"date": today, "buy": 50000.0, "sell": 0.0, "owner_cik": "a",
          "is_officer": True, "is_director": False, "is_planned": True}], today, 14
    )
    assert planned["signal_dollars"] == 0.0     # contributes nothing to the rank
    assert planned["buy_dollars"] == 50000.0    # but the raw truth is unchanged
    assert planned["net_dollars"] == 50000.0
    assert planned["planned_filings"] == 1
    assert planned["distinct_buyers"] == 0      # cannot manufacture a cluster


def test_planned_sells_do_not_penalize():
    """The sign consequence, asserted deliberately: dropping scheduled sells
    RAISES the score for issuers whose insiders sell on a plan."""
    today = date.today()
    def sale(planned):
        return sec_insider.window_activity(
            [{"date": today, "buy": 0.0, "sell": 80000.0, "owner_cik": "a",
              "is_officer": True, "is_director": False, "is_planned": planned}],
            today, 14,
        )
    assert sale(True)["signal_dollars"] == 0.0
    assert sale(False)["signal_dollars"] < 0.0
    assert sale(True)["sell_dollars"] == sale(False)["sell_dollars"] == 80000.0


def test_planned_buyers_excluded_from_cluster_count():
    """Three buyers where two are on plans is a one-insider event, not a
    cluster — otherwise scheduled buying inflates the strongest configuration
    in the literature."""
    today = date.today()
    def rec(cik, planned):
        return {"date": today, "buy": 10000.0, "sell": 0.0, "owner_cik": cik,
                "is_officer": False, "is_director": True, "is_planned": planned}
    mixed = sec_insider.window_activity(
        [rec("a", False), rec("b", True), rec("c", True)], today, 14
    )
    assert mixed["distinct_buyers"] == 1
    assert mixed["planned_filings"] == 2
    solo = sec_insider.window_activity([rec("a", False)], today, 14)
    assert mixed["signal_dollars"] == solo["signal_dollars"]


def test_records_without_the_flag_are_treated_as_discretionary():
    """Backward compatibility: pre-2023 records and failed parses carry no
    is_planned key and must keep their old behaviour, not vanish."""
    today = date.today()
    legacy = sec_insider.window_activity(
        [{"date": today, "buy": 10000.0, "sell": 0.0, "owner_cik": "a",
          "is_officer": False, "is_director": True}], today, 14
    )
    assert legacy["signal_dollars"] > 0
    assert legacy["planned_filings"] == 0


def test_sells_discounted_not_cancelling():
    """A $40k scheduled sale must not erase a $20k discretionary buy."""
    today = date.today()
    mixed = sec_insider.window_activity(
        [{"date": today, "buy": 20000.0, "sell": 0.0,
          "owner_cik": "a", "is_officer": False, "is_director": True},
         {"date": today, "buy": 0.0, "sell": 40000.0,
          "owner_cik": "b", "is_officer": True, "is_director": False}], today, 14
    )
    assert mixed["signal_dollars"] > 0          # shaped score stays positive
    assert mixed["net_dollars"] == -20000.0     # raw truth still reported


def test_xsl_prefix_stripped_for_raw_xml(tmp_path):
    client = _client_with_map({"Z": 99})
    fetched_urls = []

    class FakeResp:
        text = FORM4_XML
    def fake_get(url):
        fetched_urls.append(url)
        return FakeResp()

    with patch.object(client, "_get", side_effect=fake_get):
        client.filing_text(99, "0001-23-000456", "xslF345X05/wk-form4.xml")
        client.filing_text(99, "0001-23-000456", "plain10k.htm")
    assert fetched_urls[0].endswith("/wk-form4.xml")       # xsl viewer stripped
    assert "xsl" not in fetched_urls[0]
    assert fetched_urls[1].endswith("/plain10k.htm")       # non-xsl untouched
