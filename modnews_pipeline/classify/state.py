from __future__ import annotations

from dataclasses import dataclass, field

from modnews_pipeline.models import EventRecord, NewsItem

from .types import DiscardedRecord, EventState, PreparedItem


@dataclass(slots=True)
class ClassifyState:
    items: list[NewsItem]
    prepared: list[PreparedItem]
    events: list[EventState] = field(default_factory=list)
    discarded: list[DiscardedRecord] = field(default_factory=list)
    stage: str = "started"
    processed_candidates: int = 0
    total_candidates: int | None = None
    merged_event_count: int = 0

    @property
    def event_records(self) -> list[EventRecord]:
        return [state.record for state in self.events]

