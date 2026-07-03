from __future__ import annotations

from typing import Any

from modnews.core.task import TaskEvent


class QueueLocalMixin:
    def queue_status(self) -> dict[str, Any]:
        return {
            "counts": self.container.event_queue.status(),
            "ready": [task.id for task in self.container.event_queue.ready()],
            "completion_callbacks": self.container.completion_callbacks.list(),
        }

    def queue_list(self, states: set[str] | None = None) -> list[dict[str, Any]]:
        return [self._task_payload(task) for task in self.container.event_queue.list(states)]

    def queue_show(self, task_id: str) -> dict[str, Any]:
        task = self._task_payload(self.container.event_queue.get(task_id))
        task["result"] = self.container.event_queue.result(task_id)
        return task

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

    def _task_payload(self, task: TaskEvent) -> dict[str, Any]:
        payload = task.to_dict()
        reason = self.container.event_queue.blocked_reason(task)
        if reason:
            payload["blocked_reason"] = reason
        payload["ready"] = reason is None and task.state in {"queued", "blocked"}
        return payload
