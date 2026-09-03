"""Performance scoreboard: grades past weekly reports against benchmarks.

Each graded row answers: if you'd equal-weighted that week's top picks, how
did they do vs QQQ and IWM from the report date to now? Over time this shows
whether the composite has signal and which weeks worked.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta, timedelta
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


# Forward horizon for the recorded ICs, matching the backtest's default
# step_weeks=4 so the two pipelines are comparable. Note this makes windows
# equal-length and comparable, NOT independent: at weekly report cadence
# consecutive 28-day windows still overlap ~75%. Only the backtest's
# non-overlapping loop is statistically clean.
IC_HORIZON_DAYS = 28


def load_scores(rankings_csv: Path) -> pd.DataFrame:
    """Full shortlist score_* columns indexed by ticker (for IC computation)."""
    df = pd.read_csv(rankings_csv).set_index("ticker")
    return df[[c for c in df.columns if c.startswith("score_")]]


def window_return(closes: pd.Series, start: date) -> float | None:
    """Return from first close on/after start to the LATEST close.

    This is a to-date figure: every report graded with it shares the same right
    endpoint, so the windows are nested and of unequal length. That is the
    right question for "how have past picks done since I published them", which
    is what the scoreboard table reports. It is the WRONG input for an
    information coefficient — use fixed_horizon_return for that.
    """
    s = closes.dropna()
    s = s[s.index.date >= start]
    if len(s) < 2:
        return None
    return float(s.iloc[-1] / s.iloc[0] - 1)


def fixed_horizon_return(
    closes: pd.Series, start: date, horizon_days: int = IC_HORIZON_DAYS
) -> float | None:
    """Return over exactly [start, start + horizon_days], or None if the window
    has not closed yet.

    Equal-length, non-nested windows: the property window_return lacks and the
    one an IC needs. Mirrors backtest.window_forward_return rather than
    inventing a second scheme; the two IC pipelines in this repo should not
    measure different things.
    """
    s = closes.dropna()
    s = s[s.index.date >= start]
    if s.empty:
        return None
    end = start + timedelta(days=horizon_days)
    held = s[s.index.date <= end]
    # Refuse a partial window: if no close exists at or past the end date, the
    # horizon has not elapsed and grading it would silently shorten the window.
    if len(held) < 2 or s.index[-1].date() < end:
        return None
    return float(held.iloc[-1] / held.iloc[0] - 1)


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
            f"Mean alpha vs QQQ across {len(mean_alpha)} graded reports: "
            f"{mean_alpha.mean() * 100:+.1f}%",
            "",
            "> This is **not** a track record. Every row above is measured from "
            "its own report date to the same final close, so the windows are "
            "nested, not independent, and several reports here are only days "
            "apart. Averaging them restates one market episode N times rather "
            "than accumulating N pieces of evidence. Treat it as a description "
            "of what happened since publishing, not as evidence of skill — the "
            "53-period non-overlapping backtest is the honest measurement, and "
            "it found every signal indistinguishable from zero.",
        ]
    lines += [
        "",
        "*Grading uses each pick's first close on/after the report date; "
        "an automated research scoreboard, not investment advice.*",
        "",
    ]
    return "\n".join(lines)


def compute_ic_history(
    report_dates: list[date],
    scores_by_date: dict[date, pd.DataFrame],
    closes: pd.DataFrame,
) -> pd.DataFrame:
    """Per-report per-signal IC against a FIXED forward horizon.

    Reports too recent for the horizon to have elapsed are skipped rather than
    graded over a short window — a partial window is not a smaller sample, it
    is a different measurement.
    """
    from .adaptive import signal_ic

    rows = []
    for d in sorted(report_dates):
        scores = scores_by_date[d]
        fwd = pd.Series(
            {
                t: fixed_horizon_return(closes[t], d)
                for t in scores.index
                if t in closes.columns
            },
            dtype="float64",
        )
        if fwd.dropna().empty:
            continue
        ics = signal_ic(scores, fwd)
        if not ics.empty:
            rows.append(ics.rename(d.isoformat()))
    return pd.DataFrame(rows)


def write_adaptive_weights(
    ic_history: pd.DataFrame, reports_dir: Path
) -> Path | None:
    """Blend base weights with trailing ICs into reports/adaptive_weights.yaml.

    NOT called by the weekly run any more, and the file it writes is no longer
    picked up unless run_weekly_report.py is passed --adaptive explicitly.

    Why it was disconnected: the ICs it consumes were computed to-date, so
    every report shared a right endpoint and the windows were nested rather
    than independent. adapt_weights then averaged them as if they were separate
    draws, and MIN_PERIODS=6 counted six overlapping windows as six samples
    when the effective count was closer to one. The live output was a technical
    IC near -0.3 sustained over five consecutive reports and a weight cut to
    0.036, against a 53-period non-overlapping backtest that put every signal
    inside noise of zero. Kept for reference and for backtest.py, which drives
    adapt_weights walk-forward off genuinely non-overlapping windows.
    """
    import yaml

    from .adaptive import adapt_weights
    from .config import DEFAULT_WEIGHTS_PATH, load_weights

    base_raw = load_weights(DEFAULT_WEIGHTS_PATH)
    adapted = adapt_weights(base_raw["weights"], ic_history)
    out = dict(base_raw)
    out["weights"] = {k: round(float(v), 6) for k, v in adapted.items()}
    # rounding can nudge the sum off 1.0; push the residual into the largest weight
    residual = 1.0 - sum(out["weights"].values())
    largest = max(out["weights"], key=out["weights"].get)
    out["weights"][largest] = round(out["weights"][largest] + residual, 6)

    path = reports_dir / "adaptive_weights.yaml"
    path.write_text(
        "# GENERATED by run_scoreboard.py — IC-tilted from config/weights.yaml.\n"
        "# Edit config/weights.yaml (the base), not this file.\n"
        + yaml.safe_dump(out, sort_keys=False)
    )
    return path


def update_scoreboard(
    reports_dir: Path, top_n: int = 20, as_of: date | None = None
) -> Path | None:
    """Grade all old-enough reports, write scoreboard.md/.csv, signal_ic.csv,
    and adaptive_weights.yaml. Returns the scoreboard markdown path, or None
    when nothing is gradeable yet."""
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
    scores_by_date = {d: load_scores(rankings[d]) for d in eligible}
    all_tickers = sorted(
        {t for scores in scores_by_date.values() for t in scores.index}
    )
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

    # ICs are still recorded — they are the audit trail of what each signal did
    # — but they no longer steer live weights. write_adaptive_weights is
    # deliberately not called here; see its docstring.
    ic_history = compute_ic_history(eligible, scores_by_date, closes)
    if not ic_history.empty:
        ic_history.to_csv(reports_dir / "signal_ic.csv")
    return md_path
