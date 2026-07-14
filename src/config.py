from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "output" / "combined_news.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "output"


@dataclass(frozen=True)
class ReportLimits:
    top_news_min: int = 5
    top_news_max: int = 8
    insight_min: int = 1
    insight_max: int = 4
    deep_asset_max: int = 4
    watchlist_max: int = 3


@dataclass(frozen=True)
class ScoreWeights:
    impact: float = 0.45
    source: float = 0.04
    freshness: float = 0.10
    relevance: float = 0.16
    actionability: float = 0.10
    novelty: float = 0.15


REPORT_LIMITS = ReportLimits()
SCORE_WEIGHTS = ScoreWeights()

