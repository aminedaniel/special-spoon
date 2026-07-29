"""Technical signal: 12-1 momentum, trend, breakout proximity, volume trend.

Reworked around what actually replicates. Classic oscillator indicators
(RSI, MACD) have no robust standalone edge in the cross-sectional literature;
what does is *intermediate-term momentum measured with the most recent month
excluded* — the 12-1 convention (Jegadeesh & Titman 1993) — because the last
month is contaminated by short-term reversal. The old RSI sweet-spot and
1-month momentum subscores are gone for exactly that reason.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import combine_subscores, percentile_score

TRADING_DAYS_1M = 21
TRADING_DAYS_3M = 63
TRADING_DAYS_6M = 126
TRADING_DAYS_12M = 252


def momentum_12_1(close: pd.Series) -> float:
    """Total return from ~12 months ago to ~1 month ago, skipping the most
    recent month (short-term reversal). With less than a year of history the
    base clamps to the earliest close available."""
    base_idx = -min(len(close), TRADING_DAYS_12M)
    return float(close.iloc[-TRADING_DAYS_1M] / close.iloc[base_idx] - 1)


def _per_ticker_features(close: pd.Series, volume: pd.Series) -> dict[str, float]:
    close = close.dropna()
    if len(close) < TRADING_DAYS_6M + 5:
        return {}

    last = close.iloc[-1]
    sma50 = close.rolling(50).mean().iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else np.nan

    feats: dict[str, float] = {}
    # Trend: price above SMA50 and SMA50 above SMA200 (golden-cross style)
    feats["above_sma50"] = float(last > sma50)
    if not np.isnan(sma200):
        feats["sma50_over_sma200"] = float(sma50 > sma200)

    # The momentum that replicates: 12 months, most recent month excluded.
    feats["mom_12_1"] = momentum_12_1(close)

    # Breakout proximity: distance below 52-week high (closer is better)
    high_52w = close.iloc[-TRADING_DAYS_12M:].max()
    feats["breakout_proximity"] = last / high_52w - 1  # <= 0, closer to 0 is better

    # Volume trend: recent 21d avg volume vs prior 63d avg
    vol = volume.dropna()
    if len(vol) >= TRADING_DAYS_3M + TRADING_DAYS_1M:
        recent = vol.iloc[-TRADING_DAYS_1M:].mean()
        prior = vol.iloc[-(TRADING_DAYS_3M + TRADING_DAYS_1M):-TRADING_DAYS_1M].mean()
        if prior > 0:
            feats["volume_trend"] = recent / prior - 1
    return feats


def score(price_history: pd.DataFrame) -> pd.Series:
    """Compute per-ticker technical features then percentile-rank each
    feature cross-sectionally and average into a 0-100 score.

    `price_history` is the yfinance multi-column frame (field, ticker).
    """
    closes = price_history["Close"]
    volumes = price_history["Volume"]

    feature_rows = {
        ticker: _per_ticker_features(closes[ticker], volumes[ticker])
        for ticker in closes.columns
    }
    feats = pd.DataFrame.from_dict(feature_rows, orient="index")
    if feats.empty:
        return pd.Series(dtype=float)

    ranked = pd.DataFrame(
        {col: percentile_score(feats[col]) for col in feats.columns},
        index=feats.index,
    )
    return combine_subscores(ranked)
