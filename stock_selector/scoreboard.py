"""Performance scoreboard: grades past weekly reports against benchmarks.

Each graded row answers: if you'd equal-weighted that week's top picks, how
did they do vs QQQ and IWM from the report date to now? Over time this shows
whether the composite has signal and which weeks worked.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

BENCHMARKS = ["QQQ", "IWM"]
MIN_AGE_DAYS = 7  # a report younger than this has nothing meaningful to grade
RANKINGS_RE = re.compile(r"rankings_(\d{4}-\d{2}-\d{2})\.csv$")


def find_rankings(reports_dir: Path) -> dict[date, Path]:
    out: dict[date, Path] = {}
    for path in sorted(reports_dir.glob("rankings_*.csv")):
        m = RANKINGS_RE.search(path.name)
        if m:
            out[date.fromisoformat(m.group(1))] = path
    return out


def top_picks(rankings_csv: Path, top_n: int) -> list[str]:
    df = pd.read_csv(rankings_csv)
    if "rank" in df.columns:
        df = df.sort_values("rank")
    return df["ticker"].head(top_n).astype(str).tolist()


def window_return(closes: pd.Series, start: date) -> float | None:
    """Return from first close on/after start to the latest close."""
    s = closes.dropna()
    s = s[s.index.date >= start]
    if len(s) < 2:
        return None
    return float(s.iloc[-1] / s.iloc[0] - 1)


def grade(
    report_dates: list[date],
    picks_by_date: dict[date, list[str]],
    closes: pd.DataFrame,
) -> pd.DataFrame:
    """One row per report: equal-weight pick return vs benchmarks.

    `closes` is a (date-indexed) frame of Close prices for every pick ticker
    plus the benchmarks.
    """
    rows = []
    for d in sorted(report_dates):
        picks = picks_by_date[d]
        pick_rets = {
            t: window_return(closes[t], d) for t in picks if t in closes.columns
        }
        pick_rets = {t: r for t, r in pick_rets.items() if r is not None}
        if not pick_rets:
            log.warning("no price data to grade report %s", d)
            continue
        avg = sum(pick_rets.values()) / len(pick_rets)
        bench = {
            b: window_return(closes[b], d) if b in closes.columns else None
            for b in BENCHMARKS
        }
        qqq = bench.get("QQQ")
        rows.append(
            {
                "report_date": d.isoformat(),
                "picks_graded": len(pick_rets),
                "avg_pick_return": avg,
                "qqq_return": qqq,
                "iwm_return": bench.get("IWM"),
                "alpha_vs_qqq": (avg - qqq) if qqq is not None else None,
                "hit_rate_vs_qqq": (
                    sum(1 for r in pick_rets.values() if r > qqq) / len(pick_rets)
                    if qqq is not None
                    else None
                ),
            }
        )
    return pd.DataFrame(rows)


def render_markdown(scoreboard: pd.DataFrame, as_of: date) -> str:
    lines = [
        f"# Pick performance scoreboard — as of {as_of.isoformat()}",
        "",
        "Equal-weighted top picks per weekly report, report date → latest close.",
        "",
    ]
    if scoreboard.empty:
        lines.append("_No reports old enough to grade yet._")
        return "\n".join(lines) + "\n"

    def pct(v):
        return "—" if v is None or pd.isna(v) else f"{v * 100:+.1f}%"

    lines.append(
        "| Report | Picks | Avg return | QQQ | IWM | Alpha vs QQQ | Hit rate |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for _, row in scoreboard.iterrows():
        hit = row["hit_rate_vs_qqq"]
        lines.append(
            "| {d} | {n} | {r} | {q} | {i} | {a} | {h} |".format(
                d=row["report_date"],
                n=int(row["picks_graded"]),
                r=pct(row["avg_pick_return"]),
                q=pct(row["qqq_return"]),
                i=pct(row["iwm_return"]),
                a=pct(row["alpha_vs_qqq"]),
                h="—" if hit is None or pd.isna(hit) else f"{hit * 100:.0f}%",
            )
        )
    mean_alpha = scoreboard["alpha_vs_qqq"].dropna()
    if len(mean_alpha):
        lines += [
            "",
            f"**Mean alpha vs QQQ across {len(mean_alpha)} graded reports: "
            f"{mean_alpha.mean() * 100:+.1f}%**",
        ]
    lines += [
        "",
        "*Grading uses each pick's first close on/after the report date; "
        "an automated research scoreboard, not investment advice.*",
        "",
    ]
    return "\n".join(lines)


def update_scoreboard(
    reports_dir: Path, top_n: int = 20, as_of: date | None = None
) -> Path | None:
    """Grade all old-enough reports and write scoreboard.md/.csv. Returns the
    markdown path, or None when nothing is gradeable yet."""
    import yfinance as yf

    as_of = as_of or date.today()
    rankings = find_rankings(reports_dir)
    eligible = [
        d for d in rankings if d <= as_of - timedelta(days=MIN_AGE_DAYS)
    ]
    if not eligible:
        log.info("no reports older than %d days; skipping scoreboard", MIN_AGE_DAYS)
        return None

    picks_by_date = {d: top_picks(rankings[d], top_n) for d in eligible}
    all_tickers = sorted({t for picks in picks_by_date.values() for t in picks})
    start = min(eligible)

    closes = yf.download(
        tickers=all_tickers + BENCHMARKS,
        start=start.isoformat(),
        interval="1d",
        auto_adjust=True,
        progress=False,
    )["Close"]

    scoreboard = grade(eligible, picks_by_date, closes)
    md_path = reports_dir / "scoreboard.md"
    md_path.write_text(render_markdown(scoreboard, as_of))
    scoreboard.to_csv(reports_dir / "scoreboard.csv", index=False)
    return md_path
