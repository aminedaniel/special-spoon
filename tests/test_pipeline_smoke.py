"""End-to-end smoke test: full pipeline + report with all HTTP mocked."""

from datetime import date
from pathlib import Path
from unittest.mock import patch

from stock_selector.config import Config
from stock_selector.pipeline import run
from stock_selector.report import write_report

from conftest import TICKERS, make_fundamentals, make_price_history

FIXTURE_UNIVERSE = Path(__file__).parent / "fixtures" / "sample_universe.csv"


def _config() -> Config:
    return Config(
        weights={
            "fundamentals": 0.23,
            "technical": 0.23,
            "insider": 0.15,
            "congress": 0.05,
            "quality": 0.10,
            "filing_text": 0.08,
            "events": 0.09,
            "trends": 0.07,
        },
        thresholds={"min_market_cap": 1e8, "max_market_cap": 20e9, "max_pe": 60},
        top_n=3,
        stage_a_shortlist_size=4,
        universe=list(TICKERS),
        fred_api_key=None,
        sec_edgar_user_agent="test-suite test@example.com",
    )


@patch("stock_selector.pipeline.market_data.fetch_price_history")
@patch("stock_selector.pipeline.market_data.fetch_fundamentals")
def test_dry_run_produces_report(mock_fund, mock_prices, tmp_path):
    mock_fund.return_value = make_fundamentals()
    mock_prices.return_value = make_price_history()

    result = run(_config(), skip_stage_b=True)
    md_path, csv_path = write_report(
        result, top_n=3, output_dir=tmp_path, run_date=date(2026, 7, 17)
    )

    assert md_path.exists() and csv_path.exists()
    md = md_path.read_text()
    assert "# Weekly Stock Selector — 2026-07-17" in md
    assert "Top 3 picks" in md
    assert "not investment advice" in md
    # shortlist capped at stage_a_shortlist_size
    assert len(result.rankings) == 4
    assert list(result.rankings["rank"]) == [1, 2, 3, 4]


@patch("stock_selector.pipeline.google_trends.fetch_interest_momentum")
@patch("stock_selector.pipeline.market_data.fetch_share_change")
@patch("stock_selector.pipeline.edgar_filings.fetch_filing_similarity")
@patch("stock_selector.pipeline.edgar_filings.fetch_event_points")
@patch("stock_selector.pipeline.macro_fred.fetch_regime")
@patch("stock_selector.pipeline.congress_trades.fetch_recent_activity")
@patch("stock_selector.pipeline.sec_insider.fetch_form4_activity")
@patch("stock_selector.pipeline.market_data.fetch_price_history")
@patch("stock_selector.pipeline.market_data.fetch_fundamentals")
def test_full_run_includes_stage_b(
    mock_fund, mock_prices, mock_form4, mock_congress, mock_regime,
    mock_events, mock_sim, mock_shares, mock_trends, tmp_path
):
    import pandas as pd

    mock_fund.return_value = make_fundamentals()
    mock_prices.return_value = make_price_history()
    mock_form4.return_value = {
        t: {"net_dollars": 50000.0, "filings": 3} for t in TICKERS[:4]
    }
    mock_congress.return_value = {
        t: {"buys": 2 if t == "AAAA" else 0, "sells": 0} for t in TICKERS[:4]
    }
    mock_regime.return_value = {"label": "neutral", "detail": {"vix": 15.0}}
    mock_events.return_value = {t: (2.0 if t == "BBBB" else 0.0) for t in TICKERS[:4]}
    mock_sim.return_value = {t: 0.9 for t in TICKERS[:4]}
    mock_shares.return_value = pd.Series({t: 0.02 for t in TICKERS[:4]})
    mock_trends.return_value = {t: (1.2 if t == "CCCC" else 0.0) for t in TICKERS[:4]}

    result = run(_config(), skip_stage_b=False)

    assert "score_insider" in result.rankings.columns
    assert "score_congress" in result.rankings.columns
    assert "score_events" in result.rankings.columns
    assert "score_filing_text" in result.rankings.columns
    assert "score_quality" in result.rankings.columns
    assert "score_trends" in result.rankings.columns
    events = result.rankings["score_events"]
    assert events["BBBB"] == events.max()  # the 13D holder ranks top on events
    trends = result.rankings["score_trends"]
    assert trends["CCCC"] == trends.max()  # the search-spike name ranks top on trends
    assert result.regime["label"] == "neutral"
    # congress signal favors the ticker with disclosed buys
    congress = result.rankings["score_congress"]
    assert congress["AAAA"] == congress.max()

    md_path, _ = write_report(result, top_n=3, output_dir=tmp_path)
    assert "Market regime:** neutral" in md_path.read_text()


def test_universe_fixture_loads():
    from stock_selector.config import load_universe

    tickers = load_universe(FIXTURE_UNIVERSE)
    assert tickers == list(TICKERS)
