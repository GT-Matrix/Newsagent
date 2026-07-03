from __future__ import annotations

import json
from dataclasses import dataclass

from modnews.core.config import ClassificationConfig
from modnews.core.context import PipelineContext
from modnews.core.models import EventRecord, NewsItem
from modnews.core.progress import emit

from .batch_executor import run_batch_parallel
from .events import assign_item_to_event
from .llm_client import LlmClient
from .prompts import clustered_event_extraction_system_prompt, clustered_event_merge_system_prompt
from .retriever import EventVectorRetriever, cosine_similarity
from .types import DiscardedRecord, EventState, PreparedItem
from .utils import (
    clean_event_type,
    clean_list,
    clean_string,
    discard,
    event_payload,
    int_or_none,
    normalize_confidence,
    parse_datetime,
)


@dataclass(slots=True)
class _VectorRow:
    key: int | str
    vector: list[float]


def extract_events_from_title_clusters(
    ctx: PipelineContext,
    client: LlmClient,
    retriever: EventVectorRetriever,
    prepared: list[PreparedItem],
    config: ClassificationConfig,
    discarded: list[DiscardedRecord],
) -> list[EventState]:
    batches = _cluster_prepared_items(prepared, retriever, config.batch_size, config.batch_concurrency)
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
            source_ids = [index for index in _clean_int_list(event_row.get("source_news_ids")) if index in by_index]
            source_ids = [index for index in source_ids if by_index[index].item.classification_decision not in {"assign"}]
            if not source_ids:
                continue
            event_counter += 1
            confidence = normalize_confidence(event_row.get("confidence"))
            event = EventRecord(
                event_id=_new_event_id(ctx.scrape_date, event_counter),
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


def merge_event_clusters(
    client: LlmClient,
    retriever: EventVectorRetriever,
    events: list[EventState],
    config: ClassificationConfig,
) -> int:
    batches = _cluster_events(events, retriever, config.batch_size, config.batch_concurrency)
    emit(
        "clustered_merge_start",
        event_count=len(events),
        batch_count=len(batches),
        batch_size=config.batch_size,
        concurrency=max(1, config.batch_concurrency),
    )
    responses = _run_parallel(
        lambda args: _merge_batch(*args),
        [
            (client, batch, batch_index, len(batches))
            for batch_index, batch in enumerate(batches, start=1)
        ],
        max_workers=config.batch_concurrency,
    )

    by_id = {state.record.event_id: state for state in events}
    remove_ids: set[str] = set()
    merged_count = 0
    for response in responses:
        for group in response.get("merge_groups", []):
            target_id = clean_string(group.get("target_event_id"))
            if not target_id or target_id not in by_id or target_id in remove_ids:
                continue
            target = by_id[target_id]
            source_ids = [
                event_id
                for event_id in clean_list(group.get("source_event_ids"))
                if event_id in by_id and event_id != target_id and event_id not in remove_ids
            ]
            if not source_ids:
                continue
            label = clean_string(group.get("event_label"))
            summary = clean_string(group.get("event_summary"))
            if label:
                target.record.event_label = label
            if summary:
                target.record.event_summary = summary
            for source_id in source_ids:
                _merge_event_records(target.record, by_id[source_id].record)
                remove_ids.add(source_id)
                merged_count += 1
            emit("clustered_merge_decision", target_event_id=target_id, source_event_ids=source_ids)

    if remove_ids:
        events[:] = [state for state in events if state.record.event_id not in remove_ids]
    emit("clustered_merge_done", merged_event_count=merged_count, event_count=len(events))
    return merged_count


def _cluster_prepared_items(
    prepared: list[PreparedItem],
    retriever: EventVectorRetriever,
    batch_size: int,
    concurrency: int,
) -> list[list[PreparedItem]]:
    emit("clustered_embedding_start", target="titles", item_count=len(prepared), concurrency=max(1, concurrency))
    vectors = _embed_rows_parallel(
        [(entry.index, _title_text(entry.item)) for entry in prepared],
        retriever,
        concurrency,
    )
    emit("clustered_embedding_done", target="titles", item_count=len(vectors))
    groups = _greedy_vector_groups(vectors, batch_size)
    by_index = {entry.index: entry for entry in prepared}
    return [[by_index[int(row.key)] for row in group] for group in groups]


def _cluster_events(
    events: list[EventState],
    retriever: EventVectorRetriever,
    batch_size: int,
    concurrency: int,
) -> list[list[EventState]]:
    emit("clustered_embedding_start", target="events", item_count=len(events), concurrency=max(1, concurrency))
    vectors = _embed_rows_parallel(
        [(state.record.event_id, _event_text(state.record)) for state in events],
        retriever,
        concurrency,
    )
    emit("clustered_embedding_done", target="events", item_count=len(vectors))
    groups = _greedy_vector_groups(vectors, batch_size)
    by_id = {state.record.event_id: state for state in events}
    return [[by_id[str(row.key)] for row in group] for group in groups]


def _embed_rows_parallel(
    rows: list[tuple[int | str, str]],
    retriever: EventVectorRetriever,
    concurrency: int,
) -> list[_VectorRow]:
    workers = max(1, concurrency)
    if workers == 1:
        return [_VectorRow(key, retriever.embed_text_for_clustering(text)) for key, text in rows]
    return run_batch_parallel(
        lambda row: _VectorRow(row[0], retriever.embed_text_for_clustering(row[1])),
        rows,
        max_workers=workers,
    )


def _greedy_vector_groups(rows: list[_VectorRow], batch_size: int) -> list[list[_VectorRow]]:
    pending = rows[:]
    groups: list[list[_VectorRow]] = []
    size = max(1, batch_size)
    while pending:
        seed = pending.pop(0)
        scored = [(cosine_similarity(seed.vector, row.vector), row) for row in pending]
        scored.sort(key=lambda row: row[0], reverse=True)
        selected = [seed, *[row for _, row in scored[: size - 1]]]
        selected_keys = {row.key for row in selected}
        pending = [row for row in pending if row.key not in selected_keys]
        groups.append(selected)
    return groups


def _run_parallel(fn, args_list, *, max_workers: int) -> list[dict]:
    return run_batch_parallel(fn, args_list, max_workers=max_workers)


def _extract_batch(
    client: LlmClient,
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


def _merge_batch(
    client: LlmClient,
    batch: list[EventState],
    batch_index: int,
    batch_count: int,
) -> dict:
    payload = [event_payload(state.record) for state in batch]
    emit("clustered_merge_request", batch_index=batch_index, batch_count=batch_count, events=payload)
    response = client.complete_json(
        task="clustered_event_merge",
        messages=[
            {"role": "system", "content": clustered_event_merge_system_prompt()},
            {"role": "user", "content": json.dumps({"events": payload}, ensure_ascii=False)},
        ],
    )
    emit("clustered_merge_batch_done", batch_index=batch_index, batch_count=batch_count)
    return response


def _merge_event_records(target: EventRecord, source: EventRecord) -> None:
    target.platforms = sorted(set(target.platforms) | set(source.platforms))
    target.representative_titles = sorted(
        set(target.representative_titles) | set(source.representative_titles),
        key=lambda value: (len(value), value),
    )[:5]
    target.source_news_ids = sorted(set(target.source_news_ids) | set(source.source_news_ids))
    target.member_count = len(target.source_news_ids)
    target.key_entities = sorted(set(target.key_entities) | set(source.key_entities))
    target.event_type = target.event_type or source.event_type
    target.event_summary = target.event_summary or source.event_summary
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


def _title_text(item: NewsItem) -> str:
    return "\n".join(part for part in [item.title, item.platform, item.pubtime] if part)


def _event_text(event: EventRecord) -> str:
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


def _clean_int_list(value) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        parsed = int_or_none(item)
        if parsed is not None:
            result.append(parsed)
    return result


def _new_event_id(scrape_date: str, index: int) -> str:
    date_part = scrape_date[:10].replace("-", "")
    return f"evt_{date_part}_{index:04d}"
