"""Event points, filing-pair selection, and text similarity."""

from datetime import date

from stock_selector.data_sources.edgar_filings import (
    event_points,
    latest_report_pair,
    shingle_similarity,
    strip_html,
)

AS_OF = date(2026, 7, 1)


def _f(form, filed, items="", doc="doc.htm", accession="a"):
    return {
        "form": form,
        "filingDate": filed,
        "items": items,
        "primaryDocument": doc,
        "accessionNumber": accession,
    }


def test_event_points_activist_stake_positive():
    assert event_points([_f("SC 13D", "2026-06-01")], AS_OF) == 2.0
    assert event_points([_f("SC 13G", "2026-06-01")], AS_OF) == 1.0


def test_event_points_shelf_and_redflag_negative():
    filings = [
        _f("S-3", "2026-06-01"),
        _f("8-K", "2026-06-15", items="4.02,9.01"),
    ]
    assert event_points(filings, AS_OF) == -3.0


def test_event_points_ignores_out_of_window_and_future():
    filings = [
        _f("SC 13D", "2025-01-01"),          # far past
        _f("SC 13D", "2026-07-15"),          # future vs as_of (backtest safety)
        _f("8-K", "2026-06-15", items="5.02"),  # 8-K without 4.02
    ]
    assert event_points(filings, AS_OF) == 0.0


def test_latest_report_pair_prefers_consecutive_10qs():
    filings = [
        _f("10-Q", "2026-05-01", accession="q2"),
        _f("10-K", "2026-02-15", accession="k1"),
        _f("10-Q", "2026-02-01", accession="q1"),
    ]
    pair = latest_report_pair(filings, AS_OF)
    assert (pair[0]["accessionNumber"], pair[1]["accessionNumber"]) == ("q2", "q1")


def test_latest_report_pair_respects_as_of():
    filings = [
        _f("10-Q", "2026-08-01", accession="future"),
        _f("10-Q", "2026-05-01", accession="q2"),
        _f("10-Q", "2026-02-01", accession="q1"),
    ]
    pair = latest_report_pair(filings, AS_OF)
    assert pair[0]["accessionNumber"] == "q2"  # future filing invisible


def test_shingle_similarity_identical_and_disjoint():
    text = "the quick brown fox jumps over the lazy dog " * 20
    assert shingle_similarity(text, text) == 1.0
    other = "completely different words about financial statements entirely " * 20
    assert shingle_similarity(text, other) == 0.0


def test_strip_html():
    html = "<p>Risk&nbsp;Factors</p>  <b>have</b>   changed"
    assert strip_html(html) == " risk factors have changed"
