from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modnews.core.models import EventRecord, NewsItem


@dataclass(slots=True)
class PreparedItem:
    index: int
    item: NewsItem
    normalized_title: str
    domain: str
    pubtime: datetime | None


@dataclass(slots=True)
class DiscardedRecord:
    index: int
    title: str
    platform: str
    stage: str
    reason: str


@dataclass(slots=True)
class EventState:
    record: EventRecord


@dataclass(slots=True)
class ResumeState:
    items: list[NewsItem]
    events: list[EventState]
    discarded: list[DiscardedRecord]
    stage: str
    processed_candidates: int = 0
