from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

from modnews_pipeline.models import EventRecord, NewsItem

from .event_types import normalize_event_type
from .types import DiscardedRecord, PreparedItem


def prepare_item(index: int, item: NewsItem) -> PreparedItem:
    normalized_title = normalize_title(item.title)
    return PreparedItem(
        index=index,
        item=item,
        normalized_title=normalized_title,
        domain=urlparse(item.url).netloc.lower(),
        pubtime=parse_datetime(item.pubtime),
    )


def news_payload(entry: PreparedItem) -> dict:
    item = entry.item
    return {
        "index": entry.index,
        "title": item.title,
        "platform": item.platform,
        "pubtime": item.pubtime,
        "canonical_summary": item.canonical_summary,
        "entities": item.entities,
        "event_type": item.event_type,
        "relevance_score": item.relevance_score,
    }


def event_payload(event: EventRecord) -> dict:
    return {
        "event_id": event.event_id,
        "event_label": event.event_label,
        "event_summary": event.event_summary,
        "event_type": event.event_type,
        "key_entities": event.key_entities,
        "member_count": event.member_count,
        "platforms": event.platforms,
        "latest_pubtime": event.latest_pubtime,
        "representative_titles": event.representative_titles,
    }


def discard(index: int, item: NewsItem, stage: str, reason: str) -> DiscardedRecord:
    return DiscardedRecord(index=index, title=item.title, platform=item.platform, stage=stage, reason=reason)


def normalize_title(title: str) -> str:
    normalized = re.sub(r"\s+", " ", title).strip()
    for prefix in ("快讯", "报道", "消息称", "消息", "热搜", "全文", "视频"):
        normalized = re.sub(rf"^{re.escape(prefix)}[:：|｜-]?\s*", "", normalized, count=1)
    return normalized


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def clean_string(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def float_or_none(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_confidence(value) -> float | None:
    score = float_or_none(value)
    if score is None:
        return None
    if 1 < score <= 100:
        score = score / 100
    return max(0.0, min(1.0, score))


def clean_event_type(value) -> str:
    return normalize_event_type(value)
