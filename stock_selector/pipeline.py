"""Pipeline orchestration: Stage A (full universe, cheap data) -> shortlist ->
Stage B (expensive per-ticker sources) -> composite -> report artifacts."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import Config
from .data_sources import (
    congress_trades,
    edgar_filings,
    google_trends,
    macro_fred,
    market_data,
    sec_insider,
)
from .data_sources.edgar import EdgarClient
from .scoring import apply_quality_gate, composite_score
from .signals import congress as congress_signal
from .signals import events as events_signal
from .signals import filing_text as filing_text_signal
from .signals import fundamentals as fundamentals_signal
from .signals import insider as insider_signal
from .signals import quality as quality_signal
from .signals import technical as technical_signal
from .signals import trends as trends_signal

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    rankings: pd.DataFrame          # full scored shortlist, best first
    regime: dict                    # macro regime panel
    universe_size: int
    gated_size: int
    skipped: int
    notes: list[str] = field(default_factory=list)


def run(config: Config, skip_stage_b: bool = False) -> PipelineResult:
    notes: list[str] = []

    # ---- Stage A: cheap, full universe -------------------------------------
    fundamentals = market_data.fetch_fundamentals(config.universe)
    skipped = len(config.universe) - len(fundamentals)

    gated = apply_quality_gate(fundamentals, config.thresholds)
    if gated.empty:
        raise RuntimeError(
            "No tickers passed the quality gate — check universe and thresholds"
        )

    prices = market_data.fetch_price_history(list(gated.index))

    category_scores: dict[str, pd.Series] = {
        "fundamentals": fundamentals_signal.score(gated),
        "technical": technical_signal.score(prices).reindex(gated.index),
    }

    # Stage A composite decides the shortlist for expensive sources.
    stage_a = composite_score(
        {k: category_scores[k] for k in ("fundamentals", "technical")},
        config.weights,
    )
    shortlist = list(stage_a.head(config.stage_a_shortlist_size).index)
    log.info("Stage A shortlist: %d tickers", len(shortlist))

    # ---- Stage B: expensive, shortlist only --------------------------------
    if skip_stage_b:
        notes.append("Stage B (insider/congress/events/filing-text/quality) skipped — dry run")
    else:
        if config.sec_edgar_user_agent:
            client = EdgarClient(config.sec_edgar_user_agent)
            insider_activity = sec_insider.fetch_form4_activity(
                shortlist, client=client
            )
            category_scores["insider"] = insider_signal.score(insider_activity)
            category_scores["events"] = events_signal.score(
                edgar_filings.fetch_event_points(shortlist, client)
            )
            category_scores["filing_text"] = filing_text_signal.score(
                edgar_filings.fetch_filing_similarity(shortlist, client)
            )
        else:
            notes.append(
                "Insider/events/filing-text signals skipped: SEC_EDGAR_USER_AGENT "
                "not set (see .env.example)"
            )
        activity = congress_trades.fetch_recent_activity(shortlist)
        if activity is None:
            notes.append(
                "Congress signal unavailable: disclosure feeds unreachable or stale "
                "(no in-window transactions); its weight was redistributed"
            )
        else:
            category_scores["congress"] = congress_signal.score(activity)

        share_change = market_data.fetch_share_change(shortlist)
        category_scores["quality"] = quality_signal.score(
            gated.loc[gated.index.intersection(shortlist)], share_change
        )

        trends_momentum = google_trends.fetch_interest_momentum(shortlist)
        if any(v is not None for v in trends_momentum.values()):
            category_scores["trends"] = trends_signal.score(trends_momentum)
        else:
            notes.append(
                "Google Trends signal unavailable: no data returned (likely rate-limited); "
                "its weight was redistributed"
            )

    # ---- Composite over the shortlist --------------------------------------
    shortlist_scores = {
        name: s.reindex(shortlist) for name, s in category_scores.items()
    }
    rankings = composite_score(shortlist_scores, config.weights)

    # Attach display columns from fundamentals.
    rankings = rankings.join(gated[["shortName", "sector", "marketCap"]], how="left")

    # ---- Macro regime panel (contextual, not scored) -----------------------
    regime = (
        {"label": "skipped — dry run", "detail": {}}
        if skip_stage_b
        else macro_fred.fetch_regime(config.fred_api_key)
    )

    return PipelineResult(
        rankings=rankings,
        regime=regime,
        universe_size=len(config.universe),
        gated_size=len(gated),
        skipped=skipped,
        notes=notes,
    )
