from __future__ import annotations

from modnews.core.models import EventRecord

from .types import EventState, PreparedItem
from .utils import parse_datetime


def new_event_id(scrape_date: str, index: int) -> str:
    date_part = scrape_date[:10].replace("-", "")
    return f"evt_{date_part}_{index:04d}"


def build_event_state(
    *,
    scrape_date: str,
    index: int,
    event_label: str,
    event_summary: str | None,
    event_type: str | None,
    key_entities: list[str] | None,
    confidence: float | None,
) -> EventState:
    return EventState(
        record=EventRecord(
            event_id=new_event_id(scrape_date, index),
            event_label=event_label,
            member_count=0,
            platforms=[],
            latest_pubtime=None,
            representative_titles=[],
            first_pubtime=None,
            confidence=confidence,
            event_summary=event_summary,
            event_type=event_type,
            key_entities=key_entities or [],
            source_news_ids=[],
            last_llm_updated_at=scrape_date,
        )
    )


def assign_item_to_event(entry: PreparedItem, state: EventState, confidence: float | None) -> None:
    item = entry.item
    record = state.record
    item.event_id = record.event_id
    item.event_label = record.event_label
    item.event_confidence = confidence if confidence is not None else record.confidence
    item.classification_decision = "assign"
    item.is_ai_relevant = True

    platforms = set(record.platforms)
    platforms.add(item.platform)
    record.platforms = sorted(platforms)
    if entry.index not in record.source_news_ids:
        record.source_news_ids.append(entry.index)
    titles = [*record.representative_titles, item.title]
    record.representative_titles = sorted(set(titles), key=lambda value: (len(value), value))[:5]
    record.member_count = len(record.source_news_ids)
    if record.confidence is None or (confidence is not None and confidence > record.confidence):
        record.confidence = confidence
    if entry.pubtime:
        first = parse_datetime(record.first_pubtime)
        latest = parse_datetime(record.latest_pubtime)
        if first is None or entry.pubtime < first:
            record.first_pubtime = entry.pubtime.isoformat()
        if latest is None or entry.pubtime > latest:
            record.latest_pubtime = entry.pubtime.isoformat()


def merge_event_records(target: EventRecord, source: EventRecord) -> None:
    target.event_summary = target.event_summary or source.event_summary
    target.event_type = target.event_type or source.event_type
    target.platforms = sorted(set(target.platforms) | set(source.platforms))
    target.representative_titles = sorted(
        set(target.representative_titles) | set(source.representative_titles),
        key=lambda value: (len(value), value),
    )[:5]
    target.source_news_ids = sorted(set(target.source_news_ids) | set(source.source_news_ids))
    target.member_count = len(target.source_news_ids)
    target.key_entities = sorted(set(target.key_entities) | set(source.key_entities))
    if source.confidence is not None and (target.confidence is None or source.confidence > target.confidence):
        target.confidence = source.confidence
    first_left = parse_datetime(target.first_pubtime)
    first_right = parse_datetime(source.first_pubtime)
    if first_right and (first_left is None or first_right < first_left):
        target.first_pubtime = source.first_pubtime
    latest_left = parse_datetime(target.latest_pubtime)
    latest_right = parse_datetime(source.latest_pubtime)
    if latest_right and (latest_left is None or latest_right > latest_left):
        target.latest_pubtime = source.latest_pubtime
