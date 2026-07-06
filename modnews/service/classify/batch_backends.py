from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, TypeVar
from uuid import uuid4

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent

from .batch_items import BatchExecutionItem, describe_batch_items

T = TypeVar("T")
R = TypeVar("R")


class BatchExecutionBackend(Protocol):
    def run(self, fn: Callable[[T], R], items: list[BatchExecutionItem[T]]) -> list[R]:
        ...


class ThreadedBatchExecutionBackend:
    def run(self, fn: Callable[[T], R], items: list[BatchExecutionItem[T]]) -> list[R]:
        if not items:
            return []
        workers = max(1, min(item.metadata.max_concurrency for item in items))
        if workers == 1:
            return [fn(item.payload) for item in items]

        results: dict[int, R] = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fn, item.payload): index for index, item in enumerate(items)}
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        return [results[index] for index in range(len(items))]


@dataclass(slots=True)
class EventQueueBatchExecutionBackend:
    queue: EventQueue
    run_id: str | None = None
    step_id: str | None = None
    base_payload: dict[str, Any] = field(default_factory=dict)
    base_task: TaskEvent | None = None
    auto_drain: bool = True

    def run(self, fn: Callable[[T], R], items: list[BatchExecutionItem[T]]) -> list[R]:
        del fn
        if not items:
            return []

        if any(item.metadata.queue_task_type is None for item in items):
            raise RuntimeError("event queue batch backend requires explicit queue_task_type for all classify batch items")
        group_id = uuid4().hex
        task_ids: list[str] = []
        for item in items:
            task = self._task_for_item(group_id, item)
            task_ids.append(task.id)
            self.queue.register(task)

        if self.auto_drain:
            self.queue.drain_ready()

        summary = self.queue.group_summary(group_id)
        if summary["size"] != len(task_ids):
            raise RuntimeError(
                f"batch task group {group_id} registered {summary['size']} members, expected {len(task_ids)}"
            )
        if summary["active"] > 0:
            raise RuntimeError(
                f"batch task group {group_id} still active: {summary['by_state']}"
            )
        if summary["succeeded"] != len(task_ids):
            raise RuntimeError(
                f"batch task group {group_id} did not fully succeed: "
                f"{summary['by_state']} details={self._member_terminal_details(task_ids)}"
            )

        return [self.queue.result(task_id)["batch_result"] for task_id in task_ids]

    def _task_id(self, group_id: str, item: BatchExecutionItem[object]) -> str:
        metadata = item.metadata
        index = metadata.batch_index if metadata.batch_index is not None else metadata.item_index + 1
        prefix = str(metadata.queue_task_type)
        return f"{prefix}:{group_id}:{index}"

    def _task_for_item(self, group_id: str, item: BatchExecutionItem[object]) -> TaskEvent:
        metadata = item.metadata
        payload = {
            **self.base_payload,
            "batch": describe_batch_items([item])[0],
            "labels": metadata.labels,
        }
        if self.base_task is not None:
            payload.setdefault("parent_task_id", self.base_task.id)
            payload.setdefault("parent_task_type", self.base_task.type)
        payload.setdefault("task_group_id", group_id)
        payload["item_payload"] = item.payload
        return TaskEvent(
            id=self._task_id(group_id, item),
            type=str(metadata.queue_task_type),
            pipeline_run_id=self.run_id or (self.base_task.pipeline_run_id if self.base_task is not None else None),
            step_id=self.step_id or metadata.labels.get("stage") or metadata.task_type,
            parent_task_id=self.base_task.id if self.base_task is not None else None,
            task_group_id=group_id,
            payload=payload,
            concurrency_key=metadata.concurrency_key,
            max_concurrency=metadata.max_concurrency,
            checkpoint_policy="none",
            priority=self.base_task.priority if self.base_task is not None else 100,
            recovery_policy=self.base_task.recovery_policy if self.base_task is not None else "requeue_running",
            max_attempts=self.base_task.max_attempts if self.base_task is not None else 1,
            retry_backoff_seconds=self.base_task.retry_backoff_seconds if self.base_task is not None else 0,
        )

    def _member_terminal_details(self, task_ids: list[str]) -> list[dict[str, Any]]:
        details: list[dict[str, Any]] = []
        for task_id in task_ids:
            task = self.queue.get(task_id)
            result = self.queue.result(task_id)
            details.append(
                {
                    "task_id": task_id,
                    "state": task.state,
                    "error": result.get("error"),
                    "blocked_reason": result.get("blocked_reason"),
                    "waiting_reason": result.get("waiting_reason"),
                }
            )
        return details
