from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskBlocked
from modnews.core.task import TaskEvent

from .batch_items import BatchExecutionItem, describe_batch_items


@dataclass(frozen=True, slots=True)
class ClassifyBatchSubmission:
    group_id: str
    task_ids: list[str]


@dataclass(slots=True)
class ClassifyBatchQueueRuntime:
    queue: EventQueue
    run_id: str | None = None
    step_id: str | None = None
    base_payload: dict[str, Any] = field(default_factory=dict)
    base_task: TaskEvent | None = None
    auto_drain: bool = True

    def submit_and_collect(self, items: list[BatchExecutionItem[object]]) -> list[dict[str, Any]]:
        submission = self.submit(items)
        return self.collect_group_results(submission.group_id, submission.task_ids)

    def submit(self, items: list[BatchExecutionItem[object]]) -> ClassifyBatchSubmission:
        if not items:
            return ClassifyBatchSubmission(group_id="", task_ids=[])
        if any(item.metadata.queue_task_type is None for item in items):
            raise RuntimeError("event queue batch backend requires explicit queue_task_type for all classify batch items")

        group_id = uuid4().hex
        task_ids: list[str] = []
        for item in items:
            task = self.build_task(group_id, item)
            task_ids.append(task.id)
            self.queue.register(task)

        if self.auto_drain:
            self.queue.drain_ready()

        return ClassifyBatchSubmission(group_id=group_id, task_ids=task_ids)

    def collect_group_results(self, group_id: str, task_ids: list[str]) -> list[dict[str, Any]]:
        if not group_id:
            return []
        summary = self.queue.group_summary(group_id)
        if summary["size"] != len(task_ids):
            raise RuntimeError(
                f"batch task group {group_id} registered {summary['size']} members, expected {len(task_ids)}"
            )
        if summary["active"] > 0:
            raise TaskBlocked(
                f"batch task group {group_id} still active",
                details={"kind": "child_task_group_active", "task_group_id": group_id, "by_state": summary["by_state"]},
            )
        if summary["blocked"] > 0:
            raise TaskBlocked(
                f"batch task group {group_id} blocked",
                details={
                    "kind": "child_task_group_blocked",
                    "task_group_id": group_id,
                    "by_state": summary["by_state"],
                    "members": self.member_terminal_details(task_ids),
                },
            )
        if summary["succeeded"] != len(task_ids):
            raise RuntimeError(
                f"batch task group {group_id} did not fully succeed: "
                f"{summary['by_state']} details={self.member_terminal_details(task_ids)}"
            )

        return [self.queue.result(task_id)["batch_result"] for task_id in task_ids]

    def build_task(self, group_id: str, item: BatchExecutionItem[object]) -> TaskEvent:
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
            id=self.task_id(group_id, item),
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

    def task_id(self, group_id: str, item: BatchExecutionItem[object]) -> str:
        metadata = item.metadata
        index = metadata.batch_index if metadata.batch_index is not None else metadata.item_index + 1
        prefix = str(metadata.queue_task_type)
        return f"{prefix}:{group_id}:{index}"

    def member_terminal_details(self, task_ids: list[str]) -> list[dict[str, Any]]:
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
