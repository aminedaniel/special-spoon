"""Intangible-adjusted value: book-to-market after capitalising R&D.

GAAP expenses research and development in the year it is spent rather than
recording an asset, so reported book value systematically understates
research-heavy firms. Peters & Taylor (2017) and Eisfeldt & Papanikolaou
(2013) show that rebuilding the missing "knowledge capital" and adding it to
book equity restores much of the value factor's power in exactly the
industries where plain book-to-market looks broken.

That is this universe. Every name here is small/mid-cap US tech, where R&D is
often the single largest operating outlay, and it is the most likely reason
the plain `valuation` signal has never looked like anything: a software firm
with almost no tangible assets reads as permanently expensive on book-to-
market whether or not it is.

Construction. Knowledge capital is the undepreciated remainder of past R&D,
straight-line over five years:

    K = R&D(t) + 0.8*R&D(t-1) + 0.6*R&D(t-2) + 0.4*R&D(t-3) + 0.2*R&D(t-4)

then adjusted book equity = reported equity + K, and the score is adjusted
equity over market cap, percentile-ranked with higher (cheaper) better.

Three honest limits, none of them incidental:

1. NOT BACKTESTABLE. The statements come from yfinance snapshots, which serve
   today's figures with no point-in-time history, the same limitation that
   keeps fundamentals, valuation, quality and profitability out of the
   walk-forward. Scoring the past with today's balance sheet is lookahead
   dressed up as a result. So this signal cannot be validated the way
   residual momentum can, and that is a reason to be slower about ever giving
   it weight, not merely a footnote.

2. Yahoo's annual income statement usually carries four years, not five, so
   the 0.2 tail is normally missing. Against a steady R&D stream that
   understates K by about 7% (0.2 of a 3.0 total weight). It biases every
   ticker the same direction, and a signal that is percentile-ranked
   cross-sectionally is unmoved by a common proportional shift — it matters
   only where R&D growth rates differ sharply, which is where it silently
   favours firms whose spending ramped recently.

3. A firm with no R&D row scores NaN, not zero. "Reports no R&D" and "we could
   not find the row" are different facts; collapsing them would rank hardware
   distributors and unparsed filings as if they were the same thing.

Unscored: it enters at weight 0.0 and reports an IC like any tracked signal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import percentile_score

# Straight-line five-year amortisation of past R&D spend, newest first.
AMORTISATION_WEIGHTS = (1.0, 0.8, 0.6, 0.4, 0.2)


def knowledge_capital(rnd_annual: list[float] | None) -> float:
    """Undepreciated remainder of past R&D. NaN when there is no R&D history.

    Missing years simply contribute nothing, so a filer with four years of
    statements gets the first four weights rather than being rejected.
    """
    if not rnd_annual:
        return float("nan")
    usable = [float(v) for v in rnd_annual[: len(AMORTISATION_WEIGHTS)]]
    if not usable or any(not np.isfinite(v) for v in usable):
        return float("nan")
    return float(sum(w * v for w, v in zip(AMORTISATION_WEIGHTS, usable)))


def adjusted_book_to_market(
    rnd_annual: list[float] | None,
    book_equity: float | None,
    market_cap: float | None,
) -> float:
    """(reported equity + knowledge capital) / market cap, or NaN."""
    k = knowledge_capital(rnd_annual)
    if np.isnan(k) or book_equity is None or market_cap is None:
        return float("nan")
    equity, cap = float(book_equity), float(market_cap)
    if not np.isfinite(equity) or not np.isfinite(cap) or cap <= 0:
        return float("nan")
    return (equity + k) / cap


def score(metrics: pd.DataFrame, market_caps: pd.Series) -> pd.Series:
    """Percentile-rank adjusted book-to-market; higher (cheaper) is better."""
    if metrics.empty:
        return pd.Series(dtype=float)

    caps = pd.to_numeric(market_caps, errors="coerce").reindex(metrics.index)
    raw = pd.Series(
        {
            ticker: adjusted_book_to_market(
                metrics.at[ticker, "rnd_annual"] if "rnd_annual" in metrics else None,
                metrics.at[ticker, "book_equity"] if "book_equity" in metrics else None,
                caps.get(ticker),
            )
            for ticker in metrics.index
        },
        dtype=float,
    )
    if raw.dropna().empty:
        return pd.Series(np.nan, index=metrics.index, dtype=float)
    return percentile_score(raw)
