"""FRED macro series for the Market Regime panel (contextual, never scored).

One small batch of calls per weekly run: fed funds rate trend, 10y-2y curve,
and VIX level, classified into a coarse regime label.
"""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
SERIES = {
    "fed_funds": "DFF",
    "yield_curve_10y2y": "T10Y2Y",
    "vix": "VIXCLS",
}


def _latest_observations(series_id: str, api_key: str, count: int = 90) -> list[float]:
    resp = requests.get(
        FRED_URL,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": count,
        },
        timeout=30,
    )
    resp.raise_for_status()
    values = []
    for obs in resp.json().get("observations", []):
        try:
            values.append(float(obs["value"]))
        except (ValueError, KeyError):
            continue
    return values  # newest first


def fetch_regime(api_key: str | None) -> dict:
    """Return {"label": str, "detail": {...}} describing the macro regime.

    Fails soft: without a key or on any error, returns an 'unavailable' label
    so the report still renders.
    """
    if not api_key:
        return {"label": "unavailable (no FRED_API_KEY set)", "detail": {}}
    try:
        fed = _latest_observations(SERIES["fed_funds"], api_key)
        curve = _latest_observations(SERIES["yield_curve_10y2y"], api_key)
        vix = _latest_observations(SERIES["vix"], api_key)

        detail = {
            "fed_funds": fed[0] if fed else None,
            "fed_funds_3m_ago": fed[63] if len(fed) > 63 else None,
            "yield_curve_10y2y": curve[0] if curve else None,
            "vix": vix[0] if vix else None,
        }

        rate_now = detail["fed_funds"]
        rate_then = detail["fed_funds_3m_ago"]
        tightening = (
            rate_now is not None and rate_then is not None and rate_now > rate_then + 0.10
        )
        easing = (
            rate_now is not None and rate_then is not None and rate_now < rate_then - 0.10
        )
        inverted = detail["yield_curve_10y2y"] is not None and detail["yield_curve_10y2y"] < 0
        fearful = detail["vix"] is not None and detail["vix"] > 25

        if (tightening or inverted) and fearful:
            label = "risk-off (tightening/inverted + elevated VIX)"
        elif easing and not fearful:
            label = "risk-on (easing, calm volatility)"
        elif fearful:
            label = "cautious (elevated VIX)"
        else:
            label = "neutral"
        return {"label": label, "detail": detail}
    except Exception as exc:  # noqa: BLE001 — macro context is optional
        log.warning("FRED fetch failed: %s", exc)
        return {"label": "unavailable (FRED error)", "detail": {}}
