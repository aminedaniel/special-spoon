"""Walk-forward backtest over point-in-time signals.

Only signals that are truly reconstructable as-of a past date participate:
  - technical:      price history sliced at the rebalance date
  - stability:      trailing-year beta/idio-vol from the same sliced prices
  - earnings_drift: dated announcements (estimate + reported EPS) on/before
                    the rebalance date, via the same surprise_asof used live
  - insider:        Form 4 filings dated on/before the rebalance date
  - events:         13D/13G/shelf/8-K filings dated on/before the date
  - filing_text (opt-in, document-heavy): periodic reports filed by the date

Fundamentals, valuation, quality, and short interest are EXCLUDED:
free sources only serve current snapshots for those, and scoring the past
with today's data is lookahead bias dressed up as results.

Each rebalance: score the universe as-of that date -> take top N -> hold to
the next rebalance -> record equal-weight return vs benchmarks, plus each
signal's IC (rank correlation with the realized returns). With adaptivity
enabled, the weights for each rebalance are tilted using only ICs from
PRIOR periods — a true walk-forward of the self-improvement loop.

Known bias to keep in mind reading results: the universe is today's ticker
list, so companies that delisted or collapsed are missing (survivorship bias
inflates absolute returns; relative signal comparisons are less affected).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from . import adaptive
from .data_sources import earnings, edgar_filings, sec_insider
from .data_sources.edgar import EdgarClient
from .scoring import composite_score
from .signals import earnings_drift as earnings_drift_signal
from .signals import events as events_signal
from .signals import filing_text as filing_text_signal
from .signals import insider as insider_signal
from .signals import stability as stability_signal
from .signals import technical as technical_signal

log = logging.getLogger(__name__)

BENCHMARKS = ["QQQ", "IWM"]
BACKTEST_WEIGHTS = {  # base weights over the point-in-time signal set
    "technical": 0.30,
    "insider": 0.20,
    "earnings_drift": 0.15,
    "events": 0.15,
    "stability": 0.10,
    "filing_text": 0.10,
}
STABILITY_LOOKBACK_DAYS = 365  # match the live signal's ~1y beta window


@dataclass
class BacktestResult:
    periods: pd.DataFrame          # one row per rebalance
    ic_history: pd.DataFrame       # per-rebalance per-signal IC
    picks: pd.DataFrame            # every pick with its forward return
    weights_used: pd.DataFrame     # weights applied at each rebalance
    notes: list[str] = field(default_factory=list)


def rebalance_dates(start: date, end: date, step_weeks: int) -> list[date]:
    dates = []
    d = start
    while d + timedelta(weeks=step_weeks) <= end:
        dates.append(d)
        d += timedelta(weeks=step_weeks)
    return dates


def window_forward_return(
    closes: pd.Series, start: date, end: date
) -> float | None:
    """Close-to-close return from first close on/after start to first close
    on/after end (falls back to last available close inside the window)."""
    s = closes.dropna()
    entry = s[s.index.date >= start]
    if entry.empty:
        return None
    exit_ = s[s.index.date >= end]
    exit_px = exit_.iloc[0] if not exit_.empty else entry.iloc[-1]
    if len(entry) < 2 and exit_.empty:
        return None
    return float(exit_px / entry.iloc[0] - 1)


def technical_scores_asof(prices: pd.DataFrame, as_of: date) -> pd.Series:
    """Slice the price panel to data on/before as_of, then reuse the live
    technical signal unchanged — no lookahead by construction."""
    mask = prices.index.date <= as_of
    return technical_signal.score(prices[mask])


def stability_scores_asof(
    prices: pd.DataFrame, bench_close: pd.Series | None, as_of: date
) -> pd.Series:
    """Trailing-year beta/idio-vol as-of a date, reusing the live signal.

    The window is a *trailing* slice, not everything-to-date: the live run
    sees ~1y of history, and letting the estimation window grow with the
    backtest would quietly change what "beta" means at later rebalances.
    """
    lo = as_of - timedelta(days=STABILITY_LOOKBACK_DAYS)
    mask = (prices.index.date > lo) & (prices.index.date <= as_of)
    bench = None
    if bench_close is not None:
        b = bench_close.dropna()
        bench = b[(b.index.date > lo) & (b.index.date <= as_of)]
    return stability_signal.score(prices[mask], bench)


def form4_cap_for_window(since: date, end: date) -> int:
    """How many Form 4s per ticker the window actually needs.

    fetch_form4_history keeps the *newest* `max_filings` rows, so a cap that
    only covers recent months leaves every early rebalance with no in-window
    activity — a constant insider column that looks like a working signal and
    measures nothing. Small/mid-cap tech issuers file roughly 70-110 Form 4s a
    year, so budget 130/year plus slack and let the caller override.
    """
    years = max((end - since).days / 365.0, 1.0)
    return max(sec_insider.MAX_HISTORY_FILINGS, int(130 * years) + 40)


def collect_edgar_histories(
    client: EdgarClient,
    tickers: list[str],
    since: date,
    include_filing_text: bool,
    max_form4: int = sec_insider.MAX_HISTORY_FILINGS,
) -> dict:
    """One pass over EDGAR per ticker: Form 4 history (XML parsed once per
    filing) and the submissions rows reused by events/filing-text scoring."""
    form4: dict[str, list | None] = {}
    filings: dict[str, list[dict] | None] = {}
    log.info("Form 4 cap: %d filings/ticker since %s", max_form4, since)
    for t in tickers:
        form4[t] = sec_insider.fetch_form4_history(
            client, t, since, max_filings=max_form4
        )
        cik = client.cik_for(t)
        if cik is None:
            filings[t] = None
            continue
        try:
            filings[t] = client.recent_filings(cik)
        except Exception as exc:  # noqa: BLE001
            log.warning("submissions fetch failed for %s: %s", t, exc)
            filings[t] = None
    return {"form4": form4, "filings": filings, "text_cache": {} if include_filing_text else None}


def collect_earnings_histories(tickers: list[str]) -> dict:
    """Dated earnings frames per ticker, fetched once and windowed per
    rebalance by surprise_asof (network call — CLI-side, not in the pure loop)."""
    log.info("Fetching earnings-date history for %d tickers", len(tickers))
    return earnings.fetch_earnings_history(tickers)


def _surprise_or_none(frame, ticker: str, as_of: date) -> dict | None:
    """Per-ticker earnings parse, isolated. One malformed frame must not kill
    a multi-hour walk-forward run, and the log has to name the ticker."""
    if frame is None:
        return None
    try:
        return earnings.surprise_asof(frame, as_of)
    except Exception as exc:  # noqa: BLE001 — per-ticker failures are non-fatal
        log.warning("earnings parse failed for %s at %s: %s", ticker, as_of, exc)
        return None


def scores_asof(
    as_of: date,
    prices: pd.DataFrame,
    histories: dict,
    client: EdgarClient | None,
    include_filing_text: bool,
    bench_close: pd.Series | None = None,
) -> dict[str, pd.Series]:
    tickers = list(histories["form4"].keys())
    out: dict[str, pd.Series] = {
        "technical": technical_scores_asof(prices, as_of).reindex(tickers),
        "stability": stability_scores_asof(prices, bench_close, as_of).reindex(tickers),
        "insider": insider_signal.score(
            {
                t: sec_insider.window_activity(
                    histories["form4"][t], as_of, sec_insider.LOOKBACK_DAYS
                )
                for t in tickers
            }
        ),
        "events": events_signal.score(
            {
                t: (
                    edgar_filings.event_points(f, as_of)
                    if (f := histories["filings"][t]) is not None
                    else None
                )
                for t in tickers
            }
        ),
    }
    if histories.get("earnings") is not None:
        out["earnings_drift"] = earnings_drift_signal.score(
            {t: _surprise_or_none(histories["earnings"].get(t), t, as_of) for t in tickers}
        )
    if include_filing_text and client is not None:
        out["filing_text"] = filing_text_signal.score(
            edgar_filings.fetch_filing_similarity(
                tickers, client, as_of=as_of, text_cache=histories["text_cache"]
            )
        )
    return out


def run_backtest(
    universe: list[str],
    prices: pd.DataFrame,
    bench_closes: pd.DataFrame,
    histories: dict,
    start: date,
    end: date,
    step_weeks: int = 4,
    top_n: int = 10,
    adaptive_weights: bool = True,
    include_filing_text: bool = False,
    client: EdgarClient | None = None,
) -> BacktestResult:
    """Pure walk-forward loop over pre-fetched data (testable offline)."""
    base = dict(BACKTEST_WEIGHTS)
    if not include_filing_text:
        base.pop("filing_text")
    if histories.get("earnings") is None:
        base.pop("earnings_drift")
    total = sum(base.values())
    base = {k: v / total for k, v in base.items()}

    closes = prices["Close"]
    qqq_close = bench_closes["QQQ"] if "QQQ" in bench_closes.columns else None
    dates = rebalance_dates(start, end, step_weeks)
    period_rows, pick_rows, ic_rows, weight_rows = [], [], [], []
    ic_history = pd.DataFrame()

    for d in dates:
        weights = (
            adaptive.adapt_weights(base, ic_history)
            if adaptive_weights and not ic_history.empty
            else base
        )
        cat_scores = scores_asof(
            d, prices, histories, client, include_filing_text, bench_close=qqq_close
        )
        ranked = composite_score(cat_scores, weights)
        picks = ranked.dropna(subset=["composite"]).head(top_n)
        hold_end = d + timedelta(weeks=step_weeks)

        fwd = pd.Series(
            {
                t: window_forward_return(closes[t], d, hold_end)
                for t in picks.index
                if t in closes.columns
            },
            dtype="float64",
        ).dropna()
        if fwd.empty:
            continue

        # IC uses the WHOLE scored cross-section, not just picks.
        all_fwd = pd.Series(
            {
                t: window_forward_return(closes[t], d, hold_end)
                for t in ranked.index
                if t in closes.columns
            },
            dtype="float64",
        )
        score_cols = ranked[[c for c in ranked.columns if c.startswith("score_")]]
        ics = adaptive.signal_ic(score_cols, all_fwd)
        ic_rows.append(ics.rename(d.isoformat()))
        ic_history = pd.DataFrame(ic_rows)

        bench = {
            b: window_forward_return(bench_closes[b], d, hold_end)
            for b in BENCHMARKS
            if b in bench_closes.columns
        }
        qqq = bench.get("QQQ")
        avg = float(fwd.mean())
        period_rows.append(
            {
                "rebalance": d.isoformat(),
                "picks": len(fwd),
                "avg_return": avg,
                "qqq_return": qqq,
                "iwm_return": bench.get("IWM"),
                "alpha_vs_qqq": (avg - qqq) if qqq is not None else None,
            }
        )
        weight_rows.append(pd.Series(weights, name=d.isoformat()))
        for t, r in fwd.items():
            pick_rows.append(
                {
                    "rebalance": d.isoformat(),
                    "ticker": t,
                    "composite": float(picks.loc[t, "composite"]),
                    "forward_return": r,
                }
            )

    return BacktestResult(
        periods=pd.DataFrame(period_rows),
        ic_history=ic_history,
        picks=pd.DataFrame(pick_rows),
        weights_used=pd.DataFrame(weight_rows),
    )


def render_markdown(result: BacktestResult, top_n: int, step_weeks: int) -> str:
    p = result.periods

    def pct(v):
        return "—" if v is None or pd.isna(v) else f"{v * 100:+.1f}%"

    lines = [
        "# Backtest — point-in-time signals",
        "",
        f"Top {top_n} picks, rebalanced every {step_weeks} weeks, equal-weighted, "
        "close-to-close.",
        "",
    ]
    if p.empty:
        lines.append("_No periods could be graded (insufficient price data)._")
        return "\n".join(lines) + "\n"

    strat = (1 + p["avg_return"]).prod() - 1
    qqq = (1 + p["qqq_return"].fillna(0)).prod() - 1
    iwm = (1 + p["iwm_return"].fillna(0)).prod() - 1
    lines += [
        f"**Cumulative: strategy {pct(strat)} vs QQQ {pct(qqq)} / IWM {pct(iwm)} "
        f"over {len(p)} periods.**",
        "",
        "| Rebalance | Picks | Return | QQQ | Alpha |",
        "|---|---|---|---|---|",
    ]
    for _, row in p.iterrows():
        lines.append(
            f"| {row['rebalance']} | {int(row['picks'])} | {pct(row['avg_return'])} "
            f"| {pct(row['qqq_return'])} | {pct(row['alpha_vs_qqq'])} |"
        )

    if not result.ic_history.empty:
        lines += ["", "## Signal predictive power (mean IC)", ""]
        lines.append("| Signal | Mean IC | Periods |")
        lines.append("|---|---|---|")
        for name in result.ic_history.columns:
            ics = result.ic_history[name].dropna()
            lines.append(f"| {name} | {ics.mean():+.3f} | {len(ics)} |")
        lines += [
            "",
            "*IC = Spearman rank correlation between signal score and next-period "
            "return across the scored universe. Sustained IC above ~+0.05 is "
            "meaningful; near zero means no edge.*",
        ]

    gems = result.picks.nlargest(5, "forward_return")
    if not gems.empty:
        lines += ["", "## Biggest wins ('gems found')", ""]
        lines.append("| Picked | Ticker | Next-period return |")
        lines.append("|---|---|---|")
        for _, row in gems.iterrows():
            lines.append(
                f"| {row['rebalance']} | **{row['ticker']}** | {pct(row['forward_return'])} |"
            )
        busts = result.picks.nsmallest(3, "forward_return")
        lines += ["", "Worst picks for honesty:", ""]
        for _, row in busts.iterrows():
            lines.append(f"- {row['rebalance']} {row['ticker']}: {pct(row['forward_return'])}")

    lines += [
        "",
        "---",
        "",
        "*Caveats: survivorship bias (today's universe excludes delisted names, "
        "inflating absolute returns); fundamentals/valuation/quality/short-interest "
        "signals are excluded because free sources only provide current "
        "snapshots (using them historically would be lookahead). Research output, "
        "not investment advice.*",
        "",
    ]
    return "\n".join(lines)
