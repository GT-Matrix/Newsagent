from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.models import EventCandidate, SourceItem
from src.utils.time import parse_datetime
from src.utils.validation import as_int_list, as_string_list, normalize_confidence


def load_processed_candidates(path: Path) -> list[EventCandidate]:
    """Load the canonical output from modnews.

    The expected file is the processed PipelineResult JSON written by the
    ingest/classify stage, usually `output/combined_news.json`. It must contain
    both `events` and `items` so the report layer can keep source URLs.
    """
    with path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"Expected processed PipelineResult object in {path}")
    raw_events = data.get("events")
    raw_items = data.get("items")
    if not isinstance(raw_events, list) or not isinstance(raw_items, list):
        raise ValueError(f"Expected {path} to contain array fields: events and items")

    source_map = build_source_item_map([item for item in raw_items if isinstance(item, dict)])
    candidates: list[EventCandidate] = []
    for index, item in enumerate(raw_events, start=1):
        if not isinstance(item, dict):
            continue
        confidence, warnings = normalize_confidence(item.get("confidence"))
        original = dict(item)
        if warnings:
            original["_validation_warnings"] = warnings

        if item.get("is_duplicate") is True:
            continue
        event_id = str(item.get("event_id") or f"event_{index:04d}")
        source_items = source_map.get(event_id, [])
        source_news_ids = as_int_list(item.get("source_news_ids"))
        if not source_news_ids:
            source_news_ids = [source.source_news_id for source in source_items if source.source_news_id is not None]

        candidates.append(
            EventCandidate(
                event_id=event_id,
                event_label=str(item.get("event_label") or ""),
                member_count=int(item.get("member_count") or len(source_items) or 1),
                platforms=as_string_list(item.get("platforms")) or sorted({source.platform for source in source_items if source.platform}),
                latest_pubtime=parse_datetime(item.get("latest_pubtime")),
                representative_titles=as_string_list(item.get("representative_titles")) or [source.title for source in source_items[:5] if source.title],
                confidence=confidence,
                event_summary=str(item.get("event_summary") or ""),
                event_type=str(item.get("event_type") or ""),
                key_entities=as_string_list(item.get("key_entities")),
                source_news_ids=source_news_ids,
                last_llm_updated_at=item.get("last_llm_updated_at"),
                original=original,
                source_items=source_items,
            )
        )
    return candidates


def build_source_item_map(items: list[dict[str, Any]]) -> dict[str, list[SourceItem]]:
    source_map: dict[str, list[SourceItem]] = {}
    for index, item in enumerate(items):
        event_id = item.get("event_id")
        if not event_id:
            continue
        source = SourceItem(
            platform=str(item.get("platform") or ""),
            title=str(item.get("title") or ""),
            url=item.get("url"),
            pubtime=item.get("pubtime"),
            scrape_date=item.get("scrape_date"),
            source_news_id=index,
            classification_decision=item.get("classification_decision"),
            classification_reason=item.get("classification_reason"),
        )
        source_map.setdefault(str(event_id), []).append(source)
    return source_map
