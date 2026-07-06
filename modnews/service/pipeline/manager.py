from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.service.pipeline.registry import PipelineRegistry
from modnews.service.pipeline.run_state import update_run_state
from modnews.service.pipeline.step import PipelineStep


@dataclass(slots=True)
class PipelineManager:
    step_registry: PipelineRegistry = field(default_factory=PipelineRegistry)
    event_queue: EventQueue | None = None
    event_router: EventRouter | None = None
    ingest_registry: Any | None = None

    @property
    def steps(self) -> list[PipelineStep]:
        return self.step_registry.list()

    def bind(self, event_queue: EventQueue, event_router: EventRouter) -> None:
        self.event_queue = event_queue
        self.event_router = event_router

    def register_step(self, step: PipelineStep) -> None:
        self.step_registry.register(step)

    def start_run(self, request: dict[str, Any], *, submit: bool = False) -> dict[str, Any]:
        run_id = str(request.get("run_id") or "local")
        tasks = self.step_registry.plan_run({"run_id": run_id, "request": request})
        if self.event_queue:
            for task in tasks:
                if submit:
                    self.event_queue.submit(task)
                else:
                    self.event_queue.register(task)
        return {"run_id": run_id, "registered_tasks": [task.to_dict() for task in tasks]}

    def on_task_completed(self, event: dict[str, Any]) -> None:
        if self.event_queue:
            update_run_state(self.event_queue, event)
            self.step_registry.notify("on_task_completed", event, self.event_queue)
        self._dispatch_next(event, failed=False)

    def on_task_failed(self, event: dict[str, Any]) -> None:
        if self.event_queue:
            update_run_state(self.event_queue, event, failed=True)
        self._dispatch_next(event, failed=True)

    def on_task_blocked(self, event: dict[str, Any]) -> None:
        if self.event_queue:
            update_run_state(self.event_queue, event, blocked=True)
            self.step_registry.notify("on_task_blocked", event, self.event_queue)

    def _dispatch_next(self, event: dict[str, Any], *, failed: bool) -> None:
        if failed:
            return
        if not self.event_queue:
            return
        for task in self.step_registry.plan_followup(event):
            self.event_queue.submit(task)
