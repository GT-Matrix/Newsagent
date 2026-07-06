from __future__ import annotations

from typing import Any

from modnews.core.task import TaskEvent
from modnews.service.pipeline.read_model import build_task_detail, build_task_list_item


class QueueLocalMixin:
    def queue_status(self) -> dict[str, Any]:
        snapshot = self.container.queue_state().load()
        waiting_retry_ids = [
            task.id
            for task in self.container.event_queue.list()
            if task.next_attempt_at and self.container.event_queue.waiting_reason(task) == f"waiting until retry window {task.next_attempt_at}"
        ]
        return {
            "counts": self.container.event_queue.status(),
            "ready": [task.id for task in self.container.event_queue.ready()],
            "waiting_retry_ids": waiting_retry_ids,
            "completion_callbacks": self.container.completion_callbacks.list(),
            "snapshot": {
                "version": int(snapshot.get("version") or 1),
                "saved_at": snapshot.get("saved_at"),
                "task_count": len(snapshot.get("tasks") or []),
                "result_count": len(snapshot.get("results") or {}),
            },
        }

    def queue_list(self, states: set[str] | None = None) -> list[dict[str, Any]]:
        return [build_task_list_item(self.project_root, self.container.event_queue, task) for task in self.container.event_queue.list(states)]

    def queue_show(self, task_id: str) -> dict[str, Any]:
        return build_task_detail(self.project_root, self.container.event_queue, task_id)

    def queue_echo(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        task = TaskEvent(id=task_id, type="diagnostic.echo", payload=payload)
        self.container.event_queue.submit(task)
        return self.queue_show(task_id)

    def queue_drain(self, limit: int | None = None) -> dict[str, Any]:
        ran = self.container.event_queue.drain_ready(limit=limit)
        return {"ran": [task.to_dict() for task in ran], **self.queue_status()}

    def queue_cancel(self, task_id: str, reason: str = "cancelled by user") -> dict[str, Any]:
        task = self.container.event_queue.cancel(task_id, reason=reason)
        return {"ok": task.state == "cancelled", "task": self.queue_show(task_id)}

    def queue_retry(self, task_id: str) -> dict[str, Any]:
        task = self.container.event_queue.retry(task_id)
        if task.state == "queued":
            self.container.event_queue.drain_ready()
        return {"ok": self.container.event_queue.get(task_id).state == "succeeded", "task": self.queue_show(task_id)}

    def queue_skip(self, task_id: str, reason: str = "skipped by user") -> dict[str, Any]:
        task = self.container.event_queue.skip(task_id, reason=reason)
        return {"ok": task.state == "skipped", "task": self.queue_show(task_id)}
