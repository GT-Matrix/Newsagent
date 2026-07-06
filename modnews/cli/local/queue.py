from __future__ import annotations

from typing import Any

from modnews.core.task import TaskEvent
from modnews.service.pipeline.read_model import build_task_detail, build_task_list_item


class QueueLocalMixin:
    def queue_status(self) -> dict[str, Any]:
        snapshot = self.container.queue_state().load()
        waiting_groups = self.container.event_queue.waiting_groups()
        blocked_groups = self.container.event_queue.blocked_groups()
        return {
            "counts": self.container.event_queue.status(),
            "ready": [task.id for task in self.container.event_queue.ready()],
            "waiting_retry_ids": waiting_groups.get("retry_window", []),
            "waiting_dependency_ids": waiting_groups.get("dependency", []),
            "waiting_concurrency_ids": waiting_groups.get("concurrency", []),
            "blocked_dependency_ids": blocked_groups.get("dependency", []),
            "blocked_business_ids": blocked_groups.get("business", []),
            "next_retry_at": self.container.event_queue.next_retry_at(),
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
        items = [build_task_list_item(self.project_root, self.container.event_queue, task) for task in ran]
        return {
            "ok": True,
            "items": items,
            "ran": items,
            **self.queue_status(),
        }

    def queue_cancel(self, task_id: str, reason: str = "cancelled by user") -> dict[str, Any]:
        task = self.container.event_queue.cancel(task_id, reason=reason)
        item = self.queue_show(task_id)
        return {"ok": task.state == "cancelled", "item": item, "task": item}

    def queue_retry(self, task_id: str) -> dict[str, Any]:
        task = self.container.event_queue.retry(task_id)
        if task.state == "queued":
            self.container.event_queue.drain_ready()
        item = self.queue_show(task_id)
        return {"ok": self.container.event_queue.get(task_id).state == "succeeded", "item": item, "task": item}

    def queue_skip(self, task_id: str, reason: str = "skipped by user") -> dict[str, Any]:
        task = self.container.event_queue.skip(task_id, reason=reason)
        item = self.queue_show(task_id)
        return {"ok": task.state == "skipped", "item": item, "task": item}
