"""Technical signal: 12-1 momentum and 52-week-high proximity.

Two features, both with a published cross-sectional record:

  mom_12_1            Jegadeesh & Titman (1993). Intermediate-term momentum
                      measured with the most recent month excluded, because
                      that month is contaminated by short-term reversal. The
                      strongest surviving anomaly in the replication surveys.

  breakout_proximity  George & Hwang (2004). Nearness to the 52-week high
                      predicts returns beyond raw momentum: investors anchor
                      on the high and underreact to news that would push a
                      stock through it.

THREE FEATURES WERE REMOVED, and the reason is worth keeping. Until now this
signal averaged five features in equal weight: the two above plus
`above_sma50`, `sma50_over_sma200` (golden-cross style trend flags) and
`volume_trend`. Those three are technical-analysis folklore. They have no
robust standalone cross-sectional edge in the literature, in the same way the
RSI and MACD subscores removed earlier did not.

Equal-weighting them with the two that do replicate meant 3/5 of this signal —
and, since technical carries 0.25 of the composite, 0.15 of the whole score —
rested on features with no evidence behind them. That is precisely the defect
found in `quality`, where a survivor averaged with a casualty looked mediocre
until the two were separated. Diluting a good signal is not conservative; it
is a quiet bet that the folklore is as good as the finding.

Both survivors point the same direction by construction (a stock near its
52-week high generally has positive trailing momentum), so this is a
deliberately narrow signal rather than a diversified one. That is the
intended trade: narrow and evidenced beats broad and half-invented.

No weight changed here. technical stays at 0.25; what changed is what the
0.25 is actually measuring.
"""

from __future__ import annotations

import pandas as pd

from .base import combine_subscores, percentile_score

TRADING_DAYS_1M = 21
TRADING_DAYS_6M = 126
TRADING_DAYS_12M = 252


def momentum_12_1(close: pd.Series) -> float:
    """Total return from ~12 months ago to ~1 month ago, skipping the most
    recent month (short-term reversal). With less than a year of history the
    base clamps to the earliest close available."""
    base_idx = -min(len(close), TRADING_DAYS_12M)
    return float(close.iloc[-TRADING_DAYS_1M] / close.iloc[base_idx] - 1)


def _per_ticker_features(close: pd.Series) -> dict[str, float]:
    close = close.dropna()
    if len(close) < TRADING_DAYS_6M + 5:
        return {}

    feats: dict[str, float] = {}

    # The momentum that replicates: 12 months, most recent month excluded.
    feats["mom_12_1"] = momentum_12_1(close)

    # Breakout proximity: distance below the 52-week high (closer is better).
    high_52w = close.iloc[-TRADING_DAYS_12M:].max()
    feats["breakout_proximity"] = float(close.iloc[-1] / high_52w - 1)  # <= 0

    return feats


def score(price_history: pd.DataFrame) -> pd.Series:
    """Compute per-ticker technical features then percentile-rank each
    feature cross-sectionally and average into a 0-100 score.

    `price_history` is the yfinance multi-column frame (field, ticker). Only
    the Close panel is read; volume is no longer used by any feature.
    """
    closes = price_history["Close"]

    feature_rows = {
        ticker: _per_ticker_features(closes[ticker]) for ticker in closes.columns
    }
    feats = pd.DataFrame.from_dict(feature_rows, orient="index")
    if feats.empty:
        return pd.Series(dtype=float)

    ranked = pd.DataFrame(
        {col: percentile_score(feats[col]) for col in feats.columns},
        index=feats.index,
    )
    return combine_subscores(ranked)
