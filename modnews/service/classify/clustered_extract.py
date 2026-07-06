from __future__ import annotations

from modnews.core.event_queue import current_queue
from modnews.core.progress import emit
from modnews.core.task import current_task

from .batch_items import build_batch_items
from .batch_profile import CLUSTERED_EVENT_EXTRACTION_BATCH
from .batch_queue_runtime import ClassifyBatchQueueRuntime
from .batch_stage import LlmBatchStage, run_llm_batch_stage
from .clustered_embedding import cluster_prepared_items
from .event_state_ops import assign_item_to_event, build_event_state
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

CLUSTERED_EXTRACTION_STAGE = LlmBatchStage[list[dict[str, object]]](
    profile=CLUSTERED_EVENT_EXTRACTION_BATCH,
    llm_task="clustered_event_extraction",
    request_event="clustered_extraction_request",
    done_event="clustered_extraction_batch_done",
    system_prompt=clustered_event_extraction_system_prompt(),
    payload_key="items",
    request_event_key="items",
    build_payload=lambda batch: _batch_payload(batch),
)


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
    queue = current_queue()
    task = current_task()
    if queue is not None and task is not None:
        batch_payloads = [_batch_payload(batch) for batch in batches]
        items = build_batch_items(
            batch_payloads,
            task_type=CLUSTERED_EVENT_EXTRACTION_BATCH.task_type,
            concurrency_key=CLUSTERED_EVENT_EXTRACTION_BATCH.concurrency_key,
            max_concurrency=max(1, config.batch_concurrency),
            queue_task_type=CLUSTERED_EVENT_EXTRACTION_BATCH.queue_task_type,
            batch_indexes=list(range(1, len(batch_payloads) + 1)),
            batch_count=len(batch_payloads),
            labels=CLUSTERED_EVENT_EXTRACTION_BATCH.labels,
        )
        runtime = ClassifyBatchQueueRuntime(
            queue=queue,
            run_id=task.pipeline_run_id,
            step_id=task.step_id,
            base_payload=task.payload,
            base_task=task,
        )
        responses = runtime.submit_and_collect(items)
    else:
        responses = run_llm_batch_stage(
            client=client,
            stage=CLUSTERED_EXTRACTION_STAGE,
            batches=batches,
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
            source_ids = [index for index in clean_int_list(event_row.get("source_news_ids")) if index in by_index]
            source_ids = [index for index in source_ids if by_index[index].item.classification_decision not in {"assign"}]
            if not source_ids:
                continue
            event_counter += 1
            confidence = normalize_confidence(event_row.get("confidence"))
            state = build_event_state(
                scrape_date=ctx.scrape_date,
                index=event_counter,
                event_label=clean_string(event_row.get("event_label")) or by_index[source_ids[0]].item.title,
                event_summary=clean_string(event_row.get("event_summary")),
                event_type=clean_event_type(event_row.get("event_type")),
                key_entities=clean_list(event_row.get("key_entities")),
                confidence=confidence,
            )
            events.append(state)
            member_reasons = event_row.get("member_reasons") if isinstance(event_row.get("member_reasons"), dict) else {}
            for index in source_ids:
                entry = by_index[index]
                item = entry.item
                item.canonical_summary = state.record.event_summary or state.record.event_label
                item.entities = state.record.key_entities
                item.event_type = state.record.event_type
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


def _batch_payload(batch: list[PreparedItem]) -> list[dict[str, object]]:
    return [
        {
            "index": entry.index,
            "title": entry.item.title,
            "platform": entry.item.platform,
            "pubtime": entry.item.pubtime,
            "url_domain": entry.domain,
        }
        for entry in batch
    ]

def clean_int_list(value) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        parsed = int_or_none(item)
        if parsed is not None:
            result.append(parsed)
    return result
