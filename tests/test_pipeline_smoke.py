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
            "fundamentals": 0.30,
            "technical": 0.35,
            "insider": 0.20,
            "congress": 0.15,
        },
        thresholds={"min_market_cap": 1e8, "max_market_cap": 10e9, "max_pe": 60},
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


@patch("stock_selector.pipeline.macro_fred.fetch_regime")
@patch("stock_selector.pipeline.congress_trades.fetch_recent_activity")
@patch("stock_selector.pipeline.sec_insider.fetch_form4_counts")
@patch("stock_selector.pipeline.market_data.fetch_price_history")
@patch("stock_selector.pipeline.market_data.fetch_fundamentals")
def test_full_run_includes_stage_b(
    mock_fund, mock_prices, mock_form4, mock_congress, mock_regime, tmp_path
):
    mock_fund.return_value = make_fundamentals()
    mock_prices.return_value = make_price_history()
    mock_form4.return_value = {t: 3 for t in TICKERS[:4]}
    mock_congress.return_value = {
        t: {"buys": 2 if t == "AAAA" else 0, "sells": 0} for t in TICKERS[:4]
    }
    mock_regime.return_value = {"label": "neutral", "detail": {"vix": 15.0}}

    result = run(_config(), skip_stage_b=False)

    assert "score_insider" in result.rankings.columns
    assert "score_congress" in result.rankings.columns
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
