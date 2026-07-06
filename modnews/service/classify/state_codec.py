from __future__ import annotations

from dataclasses import asdict
from typing import Any

from modnews.core.models import EventRecord, NewsItem

from .types import DiscardedRecord, EventState, ResumeState
from .utils import clean_event_type, normalize_confidence


def build_output_payloads(
    items: list[NewsItem],
    events: list[EventRecord],
    discarded: list[DiscardedRecord],
    checkpoint_meta: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "news_with_events": [item.to_dict() for item in items],
        "events": [event.to_dict() for event in events],
        "discarded_news": [asdict(discard) for discard in discarded],
        "classification_progress": {
            "meta": checkpoint_meta or {},
            "items": [item.to_dict() for item in items],
            "events": [event.to_dict() for event in events],
            "discarded": [asdict(discard) for discard in discarded],
        },
    }


def decode_resume_state(payload: dict[str, Any], items: list[NewsItem]) -> ResumeState:
    meta = payload.get("meta", {})
    stage = str(meta.get("stage", "started"))
    if stage not in {"started", "after_clustered_event_extraction"}:
        return ResumeState(items=items, events=[], discarded=[], stage="started")
    rows = payload.get("items", [])
    restored_items = [
        NewsItem(
            platform=row["platform"],
            title=row["title"],
            url=row["url"],
            pubtime=row.get("pubtime"),
            scrape_date=row["scrape_date"],
            event_id=row.get("event_id"),
            event_label=row.get("event_label"),
            event_confidence=normalize_confidence(row.get("event_confidence")),
            is_ai_relevant=row.get("is_ai_relevant"),
            relevance_score=row.get("relevance_score"),
            canonical_summary=row.get("canonical_summary"),
            entities=row.get("entities") or [],
            event_type=clean_event_type(row.get("event_type")),
            classification_decision=row.get("classification_decision"),
            classification_reason=row.get("classification_reason"),
        )
        for row in rows
    ] if rows else items
    restored_events = [EventState(record=_decode_event_record(row)) for row in payload.get("events", [])]
    discarded = [_decode_discarded_record(row) for row in payload.get("discarded", [])]
    return ResumeState(
        items=restored_items,
        events=restored_events,
        discarded=discarded,
        stage=stage,
        processed_candidates=int(meta.get("processed_candidates") or 0),
    )


def _decode_event_record(row: dict[str, Any]) -> EventRecord:
    return EventRecord(
        event_id=row["event_id"],
        event_label=row["event_label"],
        member_count=row["member_count"],
        platforms=row.get("platforms") or [],
        latest_pubtime=row.get("latest_pubtime"),
        representative_titles=row.get("representative_titles") or [],
        first_pubtime=row.get("first_pubtime"),
        confidence=normalize_confidence(row.get("confidence")),
        event_summary=row.get("event_summary"),
        event_type=clean_event_type(row.get("event_type")),
        key_entities=row.get("key_entities") or [],
        source_news_ids=row.get("source_news_ids") or [],
        last_llm_updated_at=row.get("last_llm_updated_at"),
        is_duplicate=bool(row.get("is_duplicate", False)),
        duplicate_of_event_id=row.get("duplicate_of_event_id"),
        first_seen_date=row.get("first_seen_date"),
    )


def _decode_discarded_record(row: dict[str, Any]) -> DiscardedRecord:
    return DiscardedRecord(
        index=row["index"],
        title=row["title"],
        platform=row["platform"],
        stage=row["stage"],
        reason=row["reason"],
    )
