from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from modnews_pipeline.config import ClassificationConfig
from modnews_pipeline.models import EventRecord, NewsItem
from modnews_pipeline.progress import emit

from .types import DiscardedRecord, EventState, ResumeState
from .utils import clean_event_type, normalize_confidence


def write_outputs(
    config: ClassificationConfig,
    items: list[NewsItem],
    events: list[EventRecord],
    discarded: list[DiscardedRecord],
    checkpoint_meta: dict[str, object] | None = None,
) -> None:
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.events_output_path.parent.mkdir(parents=True, exist_ok=True)
    config.discarded_output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(
        json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    config.events_output_path.write_text(
        json.dumps([event.to_dict() for event in events], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    config.discarded_output_path.write_text(
        json.dumps([asdict(discard) for discard in discarded], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    checkpoint_path = config.checkpoint_path or (config.output_path.parent / "classification_progress.json")
    checkpoint_payload = {
        "meta": checkpoint_meta or {},
        "items": [item.to_dict() for item in items],
        "events": [event.to_dict() for event in events],
        "discarded": [asdict(discard) for discard in discarded],
    }
    checkpoint_path.write_text(
        json.dumps(checkpoint_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    emit("checkpoint", path=str(checkpoint_path), meta=checkpoint_payload["meta"])


def load_resume_state(checkpoint_path: Path | None, items: list[NewsItem]) -> ResumeState:
    if not checkpoint_path or not checkpoint_path.exists():
        return ResumeState(items=items, events=[], discarded=[], stage="started")
    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
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
    restored_events = [
        EventState(
            EventRecord(
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
        )
        for row in payload.get("events", [])
    ]
    discarded = [
        DiscardedRecord(
            index=row["index"],
            title=row["title"],
            platform=row["platform"],
            stage=row["stage"],
            reason=row["reason"],
        )
        for row in payload.get("discarded", [])
    ]
    return ResumeState(
        items=restored_items,
        events=restored_events,
        discarded=discarded,
        stage=stage,
        processed_candidates=int(meta.get("processed_candidates") or 0),
    )


def build_checkpoint_meta(
    items: list[NewsItem],
    events: list[EventRecord],
    discarded: list[DiscardedRecord],
    *,
    stage: str,
    processed_candidates: int | None = None,
    total_candidates: int | None = None,
    merged_event_count: int | None = None,
) -> dict[str, object]:
    return {
        "stage": stage,
        "item_count": len(items),
        "event_count": len(events),
        "discarded_count": len(discarded),
        "processed_candidates": processed_candidates,
        "total_candidates": total_candidates,
        "merged_event_count": merged_event_count,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
