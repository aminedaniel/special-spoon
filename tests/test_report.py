"""Report rendering: the macro panel appears only when there's something to say."""

from datetime import date

import pandas as pd

from stock_selector.pipeline import PipelineResult
from stock_selector.report import render_markdown


def _result(regime) -> PipelineResult:
    rankings = pd.DataFrame(
        {
            "score_technical": [80.0, 20.0],
            "composite": [70.0, 30.0],
            "rank": [1, 2],
            "shortName": ["Alpha Corp", "Beta Corp"],
            "sector": ["Technology", "Technology"],
            "marketCap": [1e9, 2e9],
        },
        index=["AAAA", "BBBB"],
    )
    return PipelineResult(
        rankings=rankings,
        regime=regime,
        universe_size=2,
        gated_size=2,
        skipped=0,
    )


def test_regime_panel_rendered_when_available():
    md = render_markdown(
        _result({"label": "neutral", "detail": {"vix": 15.0}}),
        top_n=2,
        run_date=date(2026, 7, 29),
    )
    assert "**Market regime:** neutral" in md
    assert "VIX 15.0" in md


def test_no_regime_means_no_panel_not_an_alarm():
    """Without a FRED key there is nothing to show. Macro is contextual and
    cannot move a rank, so the report must not open with an 'unavailable'
    line implying the run was degraded."""
    md = render_markdown(_result(None), top_n=2, run_date=date(2026, 7, 29))
    assert "Market regime" not in md
    assert "unavailable" not in md
    # The actual content is unaffected.
    assert "# Stock Selector — 2026-07-29" in md
    assert "AAAA" in md


def test_disclaimer_describes_only_live_signals():
    md = render_markdown(_result(None), top_n=2, run_date=date(2026, 7, 29))
    assert "not investment advice" in md
    # Congress was removed; the footer must not still describe it.
    assert "STOCK Act" not in md
    assert "Stock Watcher" not in md


def test_facts_section_reports_unscored_signals():
    """The report leads with signals that are computed but NOT scored — that is
    the point of the simplification, so it needs a test that fails if the
    section silently disappears."""
    import pandas as pd

    from stock_selector.report import _fact_lines

    rankings = pd.DataFrame(
        {
            "score_insider": [90.0, 50.0, 10.0, 70.0],
            "score_issuance": [20.0, 80.0, 60.0, 40.0],
        },
        index=["AAAA", "BBBB", "CCCC", "DDDD"],
    )
    lines = "\n".join(_fact_lines(rankings))
    assert "Insider buying" in lines
    assert "**AAAA**" in lines           # strongest on insider leads that row
    assert "Share count" in lines
    assert "**BBBB**" in lines


def test_facts_section_skips_near_constant_columns():
    """A column where everyone scores the same has nothing to say. Manufacturing
    a highlight from it is exactly the false precision this change removes."""
    import pandas as pd

    from stock_selector.report import _fact_lines

    flat = pd.DataFrame(
        {"score_events": [57.0, 57.0, 57.0, 57.0]},
        index=["A", "B", "C", "D"],
    )
    assert _fact_lines(flat) == []


def test_report_states_the_composite_has_no_measured_edge():
    """A ranked table implies a claim. The report must say plainly that the
    claim is not supported on this universe."""
    import pandas as pd

    from stock_selector.pipeline import PipelineResult
    from stock_selector.report import render_markdown

    rankings = pd.DataFrame(
        {
            "score_technical": [80.0, 20.0],
            "composite": [70.0, 30.0],
            "rank": [1, 2],
            "shortName": ["A Corp", "B Corp"],
            "sector": ["Technology", "Technology"],
            "marketCap": [1e9, 2e9],
        },
        index=["AAAA", "BBBB"],
    )
    md = render_markdown(
        PipelineResult(rankings=rankings, regime=None, universe_size=2,
                       gated_size=2, skipped=0),
        top_n=2,
        run_date=date(2026, 9, 6),
    )
    assert "no measured predictive power" in md
    assert "not a recommendation" in md
