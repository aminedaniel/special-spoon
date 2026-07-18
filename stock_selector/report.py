"""Render the weekly report: Markdown for reading, CSV for downstream use."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .pipeline import PipelineResult

DISCLAIMER = (
    "*This is an automated screen for research purposes, not investment advice. "
    "Congressional trades are disclosed with a 30-45 day STOCK Act lag, so that "
    "signal reflects trades made weeks earlier. Data comes from free sources "
    "(Yahoo Finance, SEC EDGAR, Senate/House Stock Watcher, FRED) with no "
    "accuracy guarantee.*"
)


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

    lines = [
        f"# Weekly Stock Selector — {run_date.isoformat()}",
        "",
        f"**Market regime:** {result.regime.get('label', 'unavailable')}",
    ]
    detail = result.regime.get("detail") or {}
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
        f"## Top {len(r)} picks",
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
