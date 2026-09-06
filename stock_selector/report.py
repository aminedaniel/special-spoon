"""Render the weekly report: Markdown for reading, CSV for downstream use."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .pipeline import PipelineResult

DISCLAIMER = (
    "*This is an automated screen for research purposes, not investment advice. "
    "Data comes from free sources (Yahoo Finance, SEC EDGAR, FRED) "
    "with no accuracy guarantee. Insider and corporate-event signals reflect SEC "
    "filings, which are themselves lagged by each form's disclosure deadline.*"
)



# Signals that are computed but no longer scored (see config/weights.yaml).
# These are the checkable, durable outputs this tool produces well, so the
# report leads with them rather than with a composite whose predictive power
# measured zero over 54 periods.
FACT_COLUMNS = {
    "score_insider": "insider buying",
    "score_events": "activist stake / corporate event",
    "score_issuance": "share count",
    "score_filing_text": "filing language",
    "score_earnings_drift": "earnings surprise",
}
FACT_TOP_N = 5


def _fact_lines(rankings: pd.DataFrame) -> list[str]:
    """Names standing out on the unscored signals, highest first.

    Deliberately reports the extremes rather than a ranking: with no measured
    edge, "these five look unusual on this dimension, go look" is a claim the
    data supports, and "these are the best stocks" is not.
    """
    out: list[str] = []
    for col, label in FACT_COLUMNS.items():
        if col not in rankings.columns:
            continue
        s = pd.to_numeric(rankings[col], errors="coerce").dropna()
        # A near-constant column has nothing to say; do not manufacture a
        # highlight out of everyone scoring the same.
        if len(s) < 3 or s.nunique() < 3:
            continue
        top = s.nlargest(min(FACT_TOP_N, len(s)))
        names = ", ".join(f"**{t}** ({v:.0f})" for t, v in top.items())
        out.append(f"- **{label.capitalize()}** — strongest: {names}")
    return out


def _fmt_cap(cap: float | None) -> str:
    if cap is None or pd.isna(cap):
        return "—"
    if cap >= 1e9:
        return f"${cap / 1e9:.1f}B"
    return f"${cap / 1e6:.0f}M"


def _fmt_score(v: float | None) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:.0f}"


def render_markdown(result: PipelineResult, top_n: int, run_date: date) -> str:
    r = result.rankings.head(top_n)
    score_cols = [c for c in result.rankings.columns if c.startswith("score_")]

    lines = [f"# Stock Selector — {run_date.isoformat()}", ""]
    # No regime data is not a fault worth announcing: macro is contextual only
    # and cannot move a single rank, so an absent panel is simply absent rather
    # than a scary "unavailable" line at the top of every report.
    regime = result.regime or {}
    if regime.get("label"):
        lines.append(f"**Market regime:** {regime['label']}")
    detail = regime.get("detail") or {}
    if detail:
        parts = []
        if detail.get("fed_funds") is not None:
            parts.append(f"fed funds {detail['fed_funds']:.2f}%")
        if detail.get("yield_curve_10y2y") is not None:
            parts.append(f"10y-2y {detail['yield_curve_10y2y']:+.2f}")
        if detail.get("vix") is not None:
            parts.append(f"VIX {detail['vix']:.1f}")
        if parts:
            lines.append(f"({', '.join(parts)})")
    lines += [
        "",
        f"Universe: {result.universe_size} tickers scanned, "
        f"{result.gated_size} passed the quality gate, "
        f"{result.skipped} skipped on data errors.",
        "",
    ]

    facts = _fact_lines(result.rankings)
    if facts:
        lines += [
            "## What changed",
            "",
            "Signals tracked but **not scored** — the specific, checkable things "
            "worth a look. Percentile within this week's shortlist.",
            "",
            *facts,
            "",
        ]

    lines += [
        f"## Top {len(r)} picks",
        "",
        "_Composite of four equal-weighted signals chosen on replication record "
        "(12-1 momentum, gross profitability, net share issuance, PEAD). It has "
        "**no measured predictive power** on this universe: a 54-period "
        "walk-forward put every measurable signal inside noise of zero, and the "
        "screen showed no alpha against IWM. Treat this as a research starting "
        "point, not a recommendation._",
        "",
    ]

    header = ["Rank", "Ticker", "Name", "Mkt cap", "Composite"] + [
        c.removeprefix("score_").capitalize() for c in score_cols
    ]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for ticker, row in r.iterrows():
        cells = [
            str(int(row["rank"])),
            f"**{ticker}**",
            str(row.get("shortName") or "—"),
            _fmt_cap(row.get("marketCap")),
            _fmt_score(row.get("composite")),
        ] + [_fmt_score(row.get(c)) for c in score_cols]
        lines.append("| " + " | ".join(cells) + " |")

    if result.notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in result.notes]

    lines += ["", "---", "", DISCLAIMER, ""]
    return "\n".join(lines)


def write_report(
    result: PipelineResult,
    top_n: int,
    output_dir: Path,
    run_date: date | None = None,
) -> tuple[Path, Path]:
    """Write report_YYYY-MM-DD.md and rankings_YYYY-MM-DD.csv; return paths."""
    run_date = run_date or date.today()
    output_dir.mkdir(parents=True, exist_ok=True)

    md_path = output_dir / f"report_{run_date.isoformat()}.md"
    csv_path = output_dir / f"rankings_{run_date.isoformat()}.csv"

    md_path.write_text(render_markdown(result, top_n, run_date))
    result.rankings.to_csv(csv_path, index_label="ticker")
    return md_path, csv_path
