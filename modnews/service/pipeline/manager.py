from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.core.task import TaskEvent


@dataclass(slots=True)
class PipelineManager:
    steps: list[Any] = field(default_factory=list)
    event_queue: EventQueue | None = None
    event_router: EventRouter | None = None
    ingest_registry: Any | None = None

    def bind(self, event_queue: EventQueue, event_router: EventRouter) -> None:
        self.event_queue = event_queue
        self.event_router = event_router

    def register_step(self, step: Any) -> None:
        self.steps.append(step)

    def start_run(self, request: dict[str, Any]) -> dict[str, Any]:
        run_id = str(request.get("run_id") or "local")
        tasks: list[TaskEvent] = []
        for step in self.steps:
            tasks.extend(step.plan({"run_id": run_id, "request": request}))
        if self.event_queue:
            for task in tasks:
                self.event_queue.submit(task)
        return {"run_id": run_id, "registered_tasks": [task.to_dict() for task in tasks]}

    def on_task_completed(self, event: dict[str, Any]) -> None:
        self._dispatch_next(event, failed=False)

    def on_task_failed(self, event: dict[str, Any]) -> None:
        self._dispatch_next(event, failed=True)

    def _dispatch_next(self, event: dict[str, Any], *, failed: bool) -> None:
        if failed:
            return
        if not self.event_queue:
            return
        for step in self.steps:
            for task in step.plan({}, completed_event=event):
                self.event_queue.submit(task)
