from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Callable

from modnews.core.models import EventRecord, NewsItem


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def news_text(item: NewsItem) -> str:
    return "\n".join(
        part
        for part in [
            item.canonical_summary,
            item.title,
            " ".join(item.entities),
            item.event_type,
        ]
        if part
    )


def event_text(event: EventRecord) -> str:
    return "\n".join(
        part
        for part in [
            event.event_label,
            event.event_summary,
            " ".join(event.key_entities),
            event.event_type,
            "\n".join(event.representative_titles),
        ]
        if part
    )


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def outside_time_window(left: datetime | None, right: datetime | None, hours: int) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) > timedelta(hours=hours)


def rank_event_candidates(
    *,
    query_vector: list[float],
    query_pubtime: datetime | None,
    events: list[EventRecord],
    limit: int,
    time_window_hours: int,
    vector_for_event: Callable[[EventRecord], list[float]],
    exclude_event_id: str | None = None,
) -> list[EventRecord]:
    scored: list[tuple[float, EventRecord]] = []
    for event in events:
        if exclude_event_id is not None and event.event_id == exclude_event_id:
            continue
        if outside_time_window(query_pubtime, parse_datetime(event.latest_pubtime), time_window_hours):
            continue
        similarity = cosine_similarity(query_vector, vector_for_event(event))
        scored.append((similarity, event))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [event for _, event in scored[:limit]]
