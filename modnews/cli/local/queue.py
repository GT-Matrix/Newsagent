from __future__ import annotations

from typing import Any

from modnews.core.task import TaskEvent


class QueueLocalMixin:
    def queue_status(self) -> dict[str, Any]:
        return {"counts": self.container.event_queue.status()}

    def queue_list(self, states: set[str] | None = None) -> list[dict[str, Any]]:
        return [task.to_dict() for task in self.container.event_queue.list(states)]

    def queue_show(self, task_id: str) -> dict[str, Any]:
        task = self.container.event_queue.get(task_id).to_dict()
        task["result"] = self.container.event_queue.result(task_id)
        return task

    def queue_echo(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        task = TaskEvent(id=task_id, type="diagnostic.echo", payload=payload)
        self.container.event_queue.dispatch(task)
        return self.queue_show(task_id)
