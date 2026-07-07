from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modnews.core.event_queue import EventQueue, current_queue
from modnews.core.task import TaskBlocked, TaskEvent

from .batch_items import build_batch_items
from .batch_profile import CLUSTERED_EMBEDDING_BATCH, CLUSTERED_EVENT_MERGE_BATCH
from .batch_queue_runtime import ClassifyBatchQueueRuntime, ClassifyBatchSubmission
from .checkpoint import build_checkpoint_meta
from .clustered_merge import (
    apply_clustered_merge_responses,
    build_event_embedding_rows,
    build_event_merge_batches_from_vectors,
)
from .runner import ClassifyRunResult, ClassifyStepResult
from .task_checkpoint import write_classify_task_checkpoint
from .task_registry import get_registered_classify_task
from .task_runtime import prepare_clustered_task_runtime


EMBEDDING_STAGE = "embedding"
MERGE_STAGE = "merge"
COMPLETED_STAGE = "completed"


@dataclass(frozen=True, slots=True)
class MergeNodeSubmission:
    stage: str
    submission: ClassifyBatchSubmission


def run_clustered_event_merge_node(task: TaskEvent) -> dict[str, object]:
    task_runtime = prepare_clustered_task_runtime(task)
    queue = _require_queue(current_queue())
    node_stage = _node_stage(task)
    if node_stage == EMBEDDING_STAGE:
        return _complete_embedding_stage(task, queue)
    if node_stage == MERGE_STAGE:
        return _complete_merge_stage(task, queue)
    return _start_merge_stage(task, task_runtime, queue)


def handle_clustered_event_merge_callback(event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]]:
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
    if parent.type != "classify.clustered_event_merge":
        return []
    stage = str(queue.result(parent.id).get("node_stage") or _node_stage(parent))
    if stage == EMBEDDING_STAGE:
        return _handle_embedding_child_event(parent, queue)
    if stage == MERGE_STAGE:
        return _handle_merge_child_event(parent, queue)
    return []


def _start_merge_stage(task: TaskEvent, task_runtime, queue: EventQueue) -> dict[str, object]:
    state = task_runtime.state
    runtime = task_runtime.runtime
    submission = _submit_embedding_children(task, queue, state.events, runtime, task_runtime.run_id)
    queue.patch_payload(
        task.id,
        {
            "node_stage": EMBEDDING_STAGE,
            "embedding_group_id": submission.submission.group_id,
            "embedding_task_ids": submission.submission.task_ids,
        },
    )
    raise TaskBlocked(
        "waiting for clustered merge embedding tasks",
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
    batches = build_event_merge_batches_from_vectors(
        task_runtime.state.events,
        vectors,
        task_runtime.runtime.config.batch_size,
    )
    submission = _submit_merge_children(task, queue, batches, task_runtime.runtime, task_runtime.run_id)
    queue.patch_payload(
        task.id,
        {
            "node_stage": MERGE_STAGE,
            "merge_group_id": submission.submission.group_id,
            "merge_task_ids": submission.submission.task_ids,
        },
    )
    raise TaskBlocked(
        "waiting for clustered merge tasks",
        details={
            "kind": "child_task_group_active",
            "node_stage": MERGE_STAGE,
            "task_group_id": submission.submission.group_id,
        },
    )


def _complete_merge_stage(task: TaskEvent, queue: EventQueue) -> dict[str, object]:
    task_runtime = prepare_clustered_task_runtime(task)
    payload = task.payload
    group_id = str(payload.get("merge_group_id") or "")
    task_ids = [str(item) for item in payload.get("merge_task_ids") or []]
    batch_runtime = _build_batch_runtime(queue, task)
    responses = batch_runtime.collect_group_results(group_id, task_ids)
    state = task_runtime.state
    state.merged_event_count = apply_clustered_merge_responses(state.events, responses)
    run_result = ClassifyRunResult(
        state=state,
        last_step_result=ClassifyStepResult(
            state=state,
            next_stage="completed",
            checkpoint_meta=build_checkpoint_meta(
                state.items,
                state.event_records,
                state.discarded,
                stage="completed",
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
        return [_mark_parent_blocked(parent, queue, reason="merge embedding child task blocked")]
    if summary["failed"] > 0:
        return []
    queue.retry(parent.id)
    queue.drain_ready()
    return [{"action": "retry_parent_task", "task_id": parent.id, "stage": EMBEDDING_STAGE}]


def _handle_merge_child_event(parent: TaskEvent, queue: EventQueue) -> list[dict[str, Any]]:
    summary = queue.group_summary(str(parent.payload.get("merge_group_id") or ""))
    if summary["active"] > 0:
        return []
    if summary["blocked"] > 0:
        return [_mark_parent_blocked(parent, queue, reason="merge child task blocked")]
    if summary["failed"] > 0:
        return []
    queue.retry(parent.id)
    queue.drain_ready()
    return [{"action": "retry_parent_task", "task_id": parent.id, "stage": MERGE_STAGE}]


def _mark_parent_blocked(parent: TaskEvent, queue: EventQueue, *, reason: str) -> dict[str, Any]:
    queue.patch_payload(parent.id, {"node_stage": _node_stage(parent)})
    return {"action": "preserve_parent_blocked", "task_id": parent.id, "reason": reason}


def _submit_embedding_children(task: TaskEvent, queue: EventQueue, events, runtime, run_id: str) -> MergeNodeSubmission:
    rows = build_event_embedding_rows(events)
    items = build_batch_items(
        rows,
        task_type=CLUSTERED_EMBEDDING_BATCH.task_type,
        concurrency_key=CLUSTERED_EMBEDDING_BATCH.concurrency_key,
        max_concurrency=max(1, runtime.config.batch_concurrency),
        queue_task_type=CLUSTERED_EMBEDDING_BATCH.queue_task_type,
        labels=CLUSTERED_EMBEDDING_BATCH.labels,
    )
    submission = _build_batch_runtime(queue, task, run_id=run_id, auto_drain=False).submit(items)
    return MergeNodeSubmission(stage=EMBEDDING_STAGE, submission=submission)


def _submit_merge_children(task: TaskEvent, queue: EventQueue, batches, runtime, run_id: str) -> MergeNodeSubmission:
    from .clustered_merge import _batch_payload

    batch_payloads = [_batch_payload(batch) for batch in batches]
    items = build_batch_items(
        batch_payloads,
        task_type=CLUSTERED_EVENT_MERGE_BATCH.task_type,
        concurrency_key=CLUSTERED_EVENT_MERGE_BATCH.concurrency_key,
        max_concurrency=max(1, runtime.config.batch_concurrency),
        queue_task_type=CLUSTERED_EVENT_MERGE_BATCH.queue_task_type,
        batch_indexes=list(range(1, len(batch_payloads) + 1)),
        batch_count=len(batch_payloads),
        labels=CLUSTERED_EVENT_MERGE_BATCH.labels,
    )
    submission = _build_batch_runtime(queue, task, run_id=run_id, auto_drain=False).submit(items)
    return MergeNodeSubmission(stage=MERGE_STAGE, submission=submission)


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
    raise RuntimeError("classify merge node requires active event queue")
