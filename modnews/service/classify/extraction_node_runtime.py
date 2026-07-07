from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modnews.core.event_queue import EventQueue, current_queue
from modnews.core.task import TaskBlocked, TaskEvent

from .batch_items import build_batch_items
from .batch_profile import CLUSTERED_EMBEDDING_BATCH, CLUSTERED_EVENT_EXTRACTION_BATCH
from .batch_queue_runtime import ClassifyBatchQueueRuntime, ClassifyBatchSubmission
from .checkpoint import build_checkpoint_meta
from .clustered_embedding import greedy_vector_groups, title_text
from .event_state_ops import assign_item_to_event, build_event_state
from .task_checkpoint import write_classify_task_checkpoint
from .task_runtime import prepare_clustered_task_runtime
from .task_registry import get_registered_classify_task
from .types import DiscardedRecord, EventState, PreparedItem
from .utils import (
    clean_event_type,
    clean_list,
    clean_string,
    discard,
    int_or_none,
    normalize_confidence,
)
from .runner import ClassifyRunResult, ClassifyStepResult


EMBEDDING_STAGE = "embedding"
EXTRACTION_STAGE = "extraction"
COMPLETED_STAGE = "completed"


@dataclass(frozen=True, slots=True)
class ExtractionNodeSubmission:
    stage: str
    submission: ClassifyBatchSubmission


def run_clustered_event_extraction_node(task: TaskEvent) -> dict[str, object]:
    task_runtime = prepare_clustered_task_runtime(task)
    queue = _require_queue(current_queue())
    node_stage = _node_stage(task)
    if node_stage == EMBEDDING_STAGE:
        return _complete_embedding_stage(task, queue)
    if node_stage == EXTRACTION_STAGE:
        return _complete_extraction_stage(task, queue)
    return _start_extraction_stage(task, task_runtime, queue)


def handle_clustered_event_extraction_callback(event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]]:
    if queue is None:
        return []
    task = event.get("task")
    if not isinstance(task, dict):
        return []
    parent_task_id = task.get("parent_task_id")
    if not parent_task_id:
        return []
    try:
        parent = queue.get(str(parent_task_id))
    except KeyError:
        return []
    if parent.type != "classify.clustered_event_extraction":
        return []
    parent_result = queue.result(parent.id)
    stage = str(parent_result.get("node_stage") or _node_stage(parent))
    if stage == EMBEDDING_STAGE:
        return _handle_embedding_child_event(parent, queue)
    if stage == EXTRACTION_STAGE:
        return _handle_extraction_child_event(parent, queue)
    return []


def _start_extraction_stage(task: TaskEvent, task_runtime, queue: EventQueue) -> dict[str, object]:
    state = task_runtime.state
    runtime = task_runtime.runtime
    state.total_candidates = len(state.prepared)
    submission = _submit_embedding_children(task, queue, state.prepared, runtime, task_runtime.run_id)
    queue.patch_payload(
        task.id,
        {
            "node_stage": EMBEDDING_STAGE,
            "embedding_group_id": submission.submission.group_id,
            "embedding_task_ids": submission.submission.task_ids,
        },
    )
    raise TaskBlocked(
        "waiting for clustered embedding tasks",
        details={
            "kind": "child_task_group_active",
            "node_stage": EMBEDDING_STAGE,
            "task_group_id": submission.submission.group_id,
        },
    )


def _complete_embedding_stage(task: TaskEvent, queue: EventQueue) -> dict[str, object]:
    task_runtime = prepare_clustered_task_runtime(task)
    payload = task.payload
    group_id = str(payload.get("embedding_group_id") or "")
    task_ids = [str(item) for item in payload.get("embedding_task_ids") or []]
    batch_runtime = _build_batch_runtime(queue, task)
    vectors = batch_runtime.collect_group_results(group_id, task_ids)
    batches = _build_title_batches_from_vectors(
        task_runtime.state.prepared,
        vectors,
        task_runtime.runtime.config.batch_size,
    )
    submission = _submit_extraction_children(task, queue, batches, task_runtime.runtime, task_runtime.run_id)
    queue.patch_payload(
        task.id,
        {
            "node_stage": EXTRACTION_STAGE,
            "extraction_group_id": submission.submission.group_id,
            "extraction_task_ids": submission.submission.task_ids,
        },
    )
    raise TaskBlocked(
        "waiting for clustered extraction tasks",
        details={
            "kind": "child_task_group_active",
            "node_stage": EXTRACTION_STAGE,
            "task_group_id": submission.submission.group_id,
        },
    )


def _complete_extraction_stage(task: TaskEvent, queue: EventQueue) -> dict[str, object]:
    task_runtime = prepare_clustered_task_runtime(task)
    payload = task.payload
    group_id = str(payload.get("extraction_group_id") or "")
    task_ids = [str(item) for item in payload.get("extraction_task_ids") or []]
    batch_runtime = _build_batch_runtime(queue, task)
    responses = batch_runtime.collect_group_results(group_id, task_ids)
    state = task_runtime.state
    _apply_extraction_responses(
        task_runtime.runtime.ctx.scrape_date,
        state.prepared,
        responses,
        state.discarded,
        state.events,
    )
    state.total_candidates = len(state.prepared)
    state.processed_candidates = len(state.prepared)
    run_result = ClassifyRunResult(
        state=state,
        last_step_result=ClassifyStepResult(
            state=state,
            next_stage="after_clustered_event_extraction",
            checkpoint_meta=build_checkpoint_meta(
                state.items,
                state.event_records,
                state.discarded,
                stage="after_clustered_event_extraction",
                processed_candidates=state.processed_candidates,
                total_candidates=state.total_candidates,
                merged_event_count=state.merged_event_count,
            ),
            stats={
                "item_count": len(state.items),
                "event_count": len(state.events),
                "discarded_count": len(state.discarded),
                "processed_candidates": state.processed_candidates,
                "total_candidates": state.total_candidates,
                "merged_event_count": state.merged_event_count,
            },
        ),
    )
    result = write_classify_task_checkpoint(
        task_runtime.project_root,
        task_runtime.run_id,
        task,
        get_registered_classify_task(task.type),
        task_runtime.input_path,
        run_result,
        task_runtime.runtime.config,
    )
    result["node_stage"] = COMPLETED_STAGE
    return result


def _handle_embedding_child_event(parent: TaskEvent, queue: EventQueue) -> list[dict[str, Any]]:
    summary = queue.group_summary(str(parent.payload.get("embedding_group_id") or ""))
    if summary["active"] > 0:
        return []
    if summary["blocked"] > 0:
        return [_mark_parent_blocked(parent, queue, reason="embedding child task blocked")]
    if summary["failed"] > 0:
        return []
    queue.retry(parent.id)
    queue.drain_ready()
    return [{"action": "retry_parent_task", "task_id": parent.id, "stage": EMBEDDING_STAGE}]


def _handle_extraction_child_event(parent: TaskEvent, queue: EventQueue) -> list[dict[str, Any]]:
    summary = queue.group_summary(str(parent.payload.get("extraction_group_id") or ""))
    if summary["active"] > 0:
        return []
    if summary["blocked"] > 0:
        return [_mark_parent_blocked(parent, queue, reason="extraction child task blocked")]
    if summary["failed"] > 0:
        return []
    queue.retry(parent.id)
    queue.drain_ready()
    return [{"action": "retry_parent_task", "task_id": parent.id, "stage": EXTRACTION_STAGE}]


def _mark_parent_blocked(parent: TaskEvent, queue: EventQueue, *, reason: str) -> dict[str, Any]:
    queue.patch_payload(parent.id, {"node_stage": _node_stage(parent)})
    return {"action": "preserve_parent_blocked", "task_id": parent.id, "reason": reason}


def _submit_embedding_children(
    task: TaskEvent,
    queue: EventQueue,
    prepared: list[PreparedItem],
    runtime,
    run_id: str,
) -> ExtractionNodeSubmission:
    rows = [{"key": entry.index, "text": title_text(entry.item)} for entry in prepared]
    items = build_batch_items(
        rows,
        task_type=CLUSTERED_EMBEDDING_BATCH.task_type,
        concurrency_key=CLUSTERED_EMBEDDING_BATCH.concurrency_key,
        max_concurrency=max(1, runtime.config.batch_concurrency),
        queue_task_type=CLUSTERED_EMBEDDING_BATCH.queue_task_type,
        labels=CLUSTERED_EMBEDDING_BATCH.labels,
    )
    submission = _build_batch_runtime(queue, task, run_id=run_id, auto_drain=False).submit(items)
    return ExtractionNodeSubmission(stage=EMBEDDING_STAGE, submission=submission)


def _submit_extraction_children(
    task: TaskEvent,
    queue: EventQueue,
    batches: list[list[PreparedItem]],
    runtime,
    run_id: str,
) -> ExtractionNodeSubmission:
    batch_payloads = [_batch_payload(batch) for batch in batches]
    items = build_batch_items(
        batch_payloads,
        task_type=CLUSTERED_EVENT_EXTRACTION_BATCH.task_type,
        concurrency_key=CLUSTERED_EVENT_EXTRACTION_BATCH.concurrency_key,
        max_concurrency=max(1, runtime.config.batch_concurrency),
        queue_task_type=CLUSTERED_EVENT_EXTRACTION_BATCH.queue_task_type,
        batch_indexes=list(range(1, len(batch_payloads) + 1)),
        batch_count=len(batch_payloads),
        labels=CLUSTERED_EVENT_EXTRACTION_BATCH.labels,
    )
    submission = _build_batch_runtime(queue, task, run_id=run_id, auto_drain=False).submit(items)
    return ExtractionNodeSubmission(stage=EXTRACTION_STAGE, submission=submission)


def _build_title_batches_from_vectors(
    prepared: list[PreparedItem],
    vector_rows: list[dict[str, Any]],
    batch_size: int,
) -> list[list[PreparedItem]]:
    from .clustered_embedding import VectorRow

    vectors = [VectorRow(key=row["key"], vector=list(row["vector"])) for row in vector_rows]
    groups = greedy_vector_groups(vectors, batch_size)
    by_index = {entry.index: entry for entry in prepared}
    return [[by_index[int(row.key)] for row in group] for group in groups]


def _apply_extraction_responses(
    scrape_date: str,
    prepared: list[PreparedItem],
    responses: list[dict[str, Any]],
    discarded: list[DiscardedRecord],
    events: list[EventState],
) -> None:
    event_counter = len(events)
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
            state = build_event_state(
                scrape_date=scrape_date,
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


def _clean_int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        parsed = int_or_none(item)
        if parsed is not None:
            result.append(parsed)
    return result


def _build_batch_runtime(
    queue: EventQueue,
    task: TaskEvent,
    *,
    run_id: str | None = None,
    auto_drain: bool = True,
) -> ClassifyBatchQueueRuntime:
    return ClassifyBatchQueueRuntime(
        queue=queue,
        run_id=run_id or task.pipeline_run_id,
        step_id=task.step_id,
        base_payload=task.payload,
        base_task=task,
        auto_drain=auto_drain,
    )


def _node_stage(task: TaskEvent) -> str:
    return str(task.payload.get("node_stage") or task.payload.get("stage") or "prepare")


def _require_queue(value: object) -> EventQueue:
    if isinstance(value, EventQueue):
        return value
    raise RuntimeError("classify extraction node requires active event queue")
