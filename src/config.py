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
    insight_max: int = 2
    deep_asset_max: int = 3
    watchlist_max: int = 5


@dataclass(frozen=True)
class ScoreWeights:
    impact: float = 0.30
    source: float = 0.20
    freshness: float = 0.15
    relevance: float = 0.15
    actionability: float = 0.10
    novelty: float = 0.10


REPORT_LIMITS = ReportLimits()
SCORE_WEIGHTS = ScoreWeights()

