from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class NewsItem:
    platform: str
    title: str
    url: str
    pubtime: str | None
    scrape_date: str
    event_id: str | None = None
    event_label: str | None = None
    event_confidence: float | None = None
    is_ai_relevant: bool | None = None
    relevance_score: int | None = None
    canonical_summary: str | None = None
    entities: list[str] = field(default_factory=list)
    event_type: str | None = None
    classification_decision: str | None = None
    classification_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PaperItem:
    platform: str
    title: str
    url: str
    pubtime: str | None
    scrape_date: str
    summary: str | None = None
    authors: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    primary_category: str | None = None
    paper_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EventRecord:
    event_id: str
    event_label: str
    member_count: int
    platforms: list[str]
    latest_pubtime: str | None
    representative_titles: list[str]
    first_pubtime: str | None = None
    confidence: float | None = None
    event_summary: str | None = None
    event_type: str | None = None
    key_entities: list[str] = field(default_factory=list)
    source_news_ids: list[int] = field(default_factory=list)
    last_llm_updated_at: str | None = None
    is_duplicate: bool = False
    duplicate_of_event_id: str | None = None
    first_seen_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StepResult:
    step: str
    item_count: int
    output_path: str | None = None
    errors: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PipelineResult:
    scrape_date: str
    items: list[NewsItem]
    events: list[EventRecord]
    steps: list[StepResult]
    output_path: Path
    papers: list[PaperItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scrape_date": self.scrape_date,
            "total": len(self.items),
            "items": [item.to_dict() for item in self.items],
            "events": [event.to_dict() for event in self.events],
            "steps": [step.to_dict() for step in self.steps],
            "papers": [paper.to_dict() for paper in self.papers],
            "output_path": str(self.output_path),
        }


def parse_datetime(value: Any) -> str | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return str(value)
