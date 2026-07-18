"""Configuration loading: .env secrets, weights.yaml, and the ticker universe."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WEIGHTS_PATH = REPO_ROOT / "config" / "weights.yaml"
DEFAULT_UNIVERSE_PATH = REPO_ROOT / "config" / "universe.csv"

WEIGHT_SUM_TOLERANCE = 1e-6


@dataclass
class Config:
    weights: dict[str, float]
    thresholds: dict[str, float]
    top_n: int
    stage_a_shortlist_size: int
    universe: list[str] = field(default_factory=list)
    fred_api_key: str | None = None
    sec_edgar_user_agent: str | None = None


def load_weights(path: Path = DEFAULT_WEIGHTS_PATH) -> dict:
    with open(path) as f:
        raw = yaml.safe_load(f)

    weights = raw.get("weights", {})
    if not weights:
        raise ValueError(f"No weights defined in {path}")
    total = sum(weights.values())
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ValueError(
            f"Signal weights must sum to 1.0, got {total:.4f} in {path}"
        )
    for name, w in weights.items():
        if w < 0:
            raise ValueError(f"Weight for {name!r} is negative: {w}")
    return raw


def load_universe(path: Path = DEFAULT_UNIVERSE_PATH) -> list[str]:
    """Read tickers from a CSV with a 'ticker' header (extra columns ignored)."""
    tickers: list[str] = []
    seen: set[str] = set()
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "ticker" not in reader.fieldnames:
            raise ValueError(f"Universe file {path} must have a 'ticker' column")
        for row in reader:
            t = (row.get("ticker") or "").strip().upper()
            if t and t not in seen:
                seen.add(t)
                tickers.append(t)
    if not tickers:
        raise ValueError(f"Universe file {path} contains no tickers")
    return tickers


def load_config(
    weights_path: Path = DEFAULT_WEIGHTS_PATH,
    universe_path: Path = DEFAULT_UNIVERSE_PATH,
) -> Config:
    load_dotenv(REPO_ROOT / ".env")
    raw = load_weights(weights_path)
    report = raw.get("report", {})
    return Config(
        weights=raw["weights"],
        thresholds=raw.get("thresholds", {}),
        top_n=int(report.get("top_n", 20)),
        stage_a_shortlist_size=int(report.get("stage_a_shortlist_size", 100)),
        universe=load_universe(universe_path),
        fred_api_key=os.getenv("FRED_API_KEY") or None,
        sec_edgar_user_agent=os.getenv("SEC_EDGAR_USER_AGENT") or None,
    )
