from __future__ import annotations

import json

from modnews.core.progress import emit

from .batch_executor import run_batch_parallel
from .clustered_embedding import cluster_prepared_items
from .events import assign_item_to_event
from .prompts import clustered_event_extraction_system_prompt
from .types import DiscardedRecord, EventState, PreparedItem
from .utils import (
    clean_event_type,
    clean_list,
    clean_string,
    discard,
    int_or_none,
    normalize_confidence,
)
from modnews.core.models import EventRecord


def extract_events_from_title_clusters(
    ctx,
    client,
    retriever,
    prepared: list[PreparedItem],
    config,
    discarded: list[DiscardedRecord],
) -> list[EventState]:
    batches = cluster_prepared_items(prepared, retriever, config.batch_size, config.batch_concurrency)
    emit(
        "clustered_extraction_start",
        item_count=len(prepared),
        batch_count=len(batches),
        batch_size=config.batch_size,
        concurrency=max(1, config.batch_concurrency),
    )
    responses = _run_parallel(
        lambda args: _extract_batch(*args),
        [
            (client, batch, batch_index, len(batches))
            for batch_index, batch in enumerate(batches, start=1)
        ],
        max_workers=config.batch_concurrency,
        task_type="classify.clustered_event_extraction.batch",
        labels={"stage": "clustered_event_extraction"},
    )

    events: list[EventState] = []
    event_counter = 0
    seen_discarded: set[int] = {record.index for record in discarded}
    by_index = {entry.index: entry for entry in prepared}

    for response in responses:
        for discarded_row in response.get("discards", []):
            index = int_or_none(discarded_row.get("index"))
            if index is None or index not in by_index or index in seen_discarded:
                continue
            entry = by_index[index]
            item = entry.item
            item.classification_decision = "discard"
            item.is_ai_relevant = False
            item.relevance_score = int_or_none(discarded_row.get("relevance_score"))
            item.classification_reason = clean_string(discarded_row.get("reason")) or "LLM discarded in clustered extraction"
            discarded.append(discard(index, item, "clustered_title_discard", item.classification_reason))
            seen_discarded.add(index)

        for suspect in response.get("suspects", []):
            index = int_or_none(suspect.get("index"))
            if index is None or index not in by_index or index in seen_discarded:
                continue
            entry = by_index[index]
            item = entry.item
            item.classification_decision = "suspect"
            item.is_ai_relevant = None
            item.relevance_score = int_or_none(suspect.get("relevance_score"))
            item.classification_reason = clean_string(suspect.get("reason")) or "title-only suspected AI item"
            discarded.append(discard(index, item, "clustered_title_suspect", item.classification_reason))
            seen_discarded.add(index)

        for event_row in response.get("events", []):
            source_ids = [index for index in clean_int_list(event_row.get("source_news_ids")) if index in by_index]
            source_ids = [index for index in source_ids if by_index[index].item.classification_decision not in {"assign"}]
            if not source_ids:
                continue
            event_counter += 1
            confidence = normalize_confidence(event_row.get("confidence"))
            event = EventRecord(
                event_id=new_event_id(ctx.scrape_date, event_counter),
                event_label=clean_string(event_row.get("event_label")) or by_index[source_ids[0]].item.title,
                member_count=0,
                platforms=[],
                latest_pubtime=None,
                representative_titles=[],
                first_pubtime=None,
                confidence=confidence,
                event_summary=clean_string(event_row.get("event_summary")),
                event_type=clean_event_type(event_row.get("event_type")),
                key_entities=clean_list(event_row.get("key_entities")),
                source_news_ids=[],
                last_llm_updated_at=ctx.scrape_date,
            )
            state = EventState(record=event)
            events.append(state)
            member_reasons = event_row.get("member_reasons") if isinstance(event_row.get("member_reasons"), dict) else {}
            for index in source_ids:
                entry = by_index[index]
                item = entry.item
                item.canonical_summary = event.event_summary or event.event_label
                item.entities = event.key_entities
                item.event_type = event.event_type
                item.relevance_score = item.relevance_score or 90
                item.classification_reason = clean_string(member_reasons.get(str(index))) or "clustered title extraction"
                assign_item_to_event(entry, state, confidence)

    for entry in prepared:
        item = entry.item
        if item.classification_decision in {"assign", "suspect", "discard"}:
            continue
        item.classification_decision = "discard"
        item.is_ai_relevant = False
        item.classification_reason = "LLM omitted item from clustered extraction response"
        discarded.append(discard(entry.index, item, "clustered_title_omitted", item.classification_reason))

    emit("clustered_extraction_done", event_count=len(events), discarded_count=len(discarded))
    return events


def _run_parallel(fn, args_list, *, max_workers: int, task_type: str, labels: dict[str, str]) -> list[dict]:
    return run_batch_parallel(
        fn,
        args_list,
        max_workers=max_workers,
        task_type=task_type,
        concurrency_key="classify.llm",
        batch_indexes=list(range(1, len(args_list) + 1)),
        batch_count=len(args_list),
        labels=labels,
    )


def _extract_batch(
    client,
    batch: list[PreparedItem],
    batch_index: int,
    batch_count: int,
) -> dict:
    payload = [
        {
            "index": entry.index,
            "title": entry.item.title,
            "platform": entry.item.platform,
            "pubtime": entry.item.pubtime,
            "url_domain": entry.domain,
        }
        for entry in batch
    ]
    emit("clustered_extraction_request", batch_index=batch_index, batch_count=batch_count, items=payload)
    response = client.complete_json(
        task="clustered_event_extraction",
        messages=[
            {"role": "system", "content": clustered_event_extraction_system_prompt()},
            {"role": "user", "content": json.dumps({"items": payload}, ensure_ascii=False)},
        ],
    )
    emit("clustered_extraction_batch_done", batch_index=batch_index, batch_count=batch_count)
    return response


def clean_int_list(value) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        parsed = int_or_none(item)
        if parsed is not None:
            result.append(parsed)
    return result


def new_event_id(scrape_date: str, index: int) -> str:
    date_part = scrape_date[:10].replace("-", "")
    return f"evt_{date_part}_{index:04d}"
