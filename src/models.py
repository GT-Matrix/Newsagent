from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal


ContentLayer = Literal["news", "insight", "deep_asset", "noise"]
VerifyStatus = Literal["verified", "single_source", "rumor", "needs_review"]
ReportSection = Literal["top_news", "insight", "deep_asset", "watchlist"]


@dataclass
class SourceItem:
    platform: str
    title: str
    url: str | None = None
    pubtime: str | None = None
    scrape_date: str | None = None
    source_news_id: int | None = None
    classification_decision: str | None = None
    classification_reason: str | None = None


@dataclass
class EventCandidate:
    event_id: str
    event_label: str
    member_count: int
    platforms: list[str]
    latest_pubtime: datetime | None
    representative_titles: list[str]
    confidence: float
    event_summary: str
    event_type: str
    key_entities: list[str]
    source_news_ids: list[int]
    last_llm_updated_at: str | None
    original: dict[str, Any]
    source_items: list[SourceItem] = field(default_factory=list)


@dataclass
class ScoreBreakdown:
    importance_score: float
    source_score: float
    freshness_score: float
    relevance_score: float
    final_score: float
    score_reason: str


@dataclass
class EnrichedEvent:
    event_id: str
    title: str
    one_sentence: str
    why_important: str
    content_layer: ContentLayer
    topic: str
    normalized_event_type: str
    entities: list[str]
    platforms: list[str]
    member_count: int
    source_news_ids: list[int]
    source_items: list[dict[str, Any]]
    latest_pubtime: str | None
    confidence: float
    importance_score: float
    source_score: float
    freshness_score: float
    relevance_score: float
    final_score: float
    score_reason: str
    verify_status: VerifyStatus
    verify_reason: str
    text_quality: str
    report_section: ReportSection | None = None
    should_include_report: bool = False
    report_reason: str = ""
    warnings: list[str] = field(default_factory=list)
    original_event: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
