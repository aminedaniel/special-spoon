"""Technical signal: trend, momentum, RSI positioning, breakout proximity,
and volume trend — all hand-rolled in pandas from daily OHLCV."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import combine_subscores, percentile_score

TRADING_DAYS_1M = 21
TRADING_DAYS_3M = 63
TRADING_DAYS_6M = 126


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss
    out = 100 - (100 / (1 + rs))
    # flat-loss edge case: all-gain windows -> RSI 100
    return out.where(avg_loss != 0, 100.0)


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

    # Momentum: simple total returns over 1/3/6 months
    feats["mom_1m"] = last / close.iloc[-TRADING_DAYS_1M] - 1
    feats["mom_3m"] = last / close.iloc[-TRADING_DAYS_3M] - 1
    feats["mom_6m"] = last / close.iloc[-TRADING_DAYS_6M] - 1

    # RSI sweet spot: prefer 50-70 (uptrend, not overbought).
    r = rsi(close).iloc[-1]
    if not np.isnan(r):
        feats["rsi_sweet"] = -abs(r - 60.0)  # peak score at RSI 60

    # Breakout proximity: distance below 52-week high (closer is better)
    high_52w = close.iloc[-252:].max() if len(close) >= 252 else close.max()
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
