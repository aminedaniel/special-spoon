"""Event points, filing-pair selection, and text similarity."""

from datetime import date

from stock_selector.data_sources.edgar_filings import (
    event_points,
    is_quiet_dump,
    latest_report_pair,
    shingle_similarity,
    strip_html,
)

AS_OF = date(2026, 7, 1)


def _f(form, filed, items="", doc="doc.htm", accession="a", accepted=None):
    return {
        "form": form,
        "filingDate": filed,
        "items": items,
        "primaryDocument": doc,
        "accessionNumber": accession,
        "acceptanceDateTime": accepted,
    }


def test_event_points_activist_stake_positive():
    assert event_points([_f("SC 13D", "2026-06-01")], AS_OF) == 2.0
    assert event_points([_f("SC 13D/A", "2026-06-01")], AS_OF) == 2.0


def test_event_points_ignores_passive_13g():
    """13G is 94% of stake filings and near-universal over a 365d window, so
    scoring it adds the same constant to everyone and cannot rank."""
    assert event_points([_f("SC 13G", "2026-06-01")], AS_OF) == 0.0
    assert event_points([_f("SC 13G/A", "2026-06-01")], AS_OF) == 0.0


def test_event_points_activist_is_capped_not_summed():
    """13D/A amendments outnumber initial 13Ds 4:1; summing them would let one
    long-running campaign accrue an unbounded score."""
    many = [
        _f("SC 13D", "2026-06-01"),
        _f("SC 13D/A", "2026-05-01"),
        _f("SC 13D/A", "2026-04-01"),
        _f("SC 13D/A", "2026-03-01"),
    ]
    assert event_points(many, AS_OF) == 2.0


def test_event_points_stake_window_reaches_back_a_year():
    """The February filing cluster is why: a 120d window ending mid-year saw
    none of it (measured: 0 in-window across 93 tickers)."""
    february = _f("SC 13D", "2026-02-12")          # 139 days before AS_OF
    assert event_points([february], AS_OF) == 2.0
    too_old = _f("SC 13D", "2025-06-01")           # 395 days — outside 365d
    assert event_points([too_old], AS_OF) == 0.0


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


def test_shelf_variants_all_count():
    """The live diagnostic found zero plain "S-3" strings in a decade of
    issuer feeds — real filers use S-3ASR / F-3 etc. All must score."""
    for form in ("S-3", "S-3ASR", "S-3MEF", "F-3", "F-3ASR"):
        assert event_points([_f(form, "2026-06-01")], AS_OF) == -1.0


def test_quiet_dump_detection():
    assert is_quiet_dump("2026-06-19T17:30:00")      # Friday after the close
    assert is_quiet_dump("2026-06-20T09:00:00")      # Saturday
    assert not is_quiet_dump("2026-06-19T10:00:00")  # Friday mid-session
    assert not is_quiet_dump("2026-06-17T18:00:00")  # Wednesday evening
    assert not is_quiet_dump(None)
    assert not is_quiet_dump("garbage")


def test_friday_night_8k_penalized():
    quiet = event_points(
        [_f("8-K", "2026-06-19", accepted="2026-06-19T17:45:00")], AS_OF
    )
    loud = event_points(
        [_f("8-K", "2026-06-17", accepted="2026-06-17T09:00:00")], AS_OF
    )
    assert quiet == -0.5 and loud == 0.0
    # A 4.02 dumped on Friday night stacks both penalties.
    both = event_points(
        [_f("8-K", "2026-06-19", items="4.02", accepted="2026-06-19T17:45:00")],
        AS_OF,
    )
    assert both == -2.5
