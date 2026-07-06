from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.service.pipeline.manager_support import (
    dispatch_followup_tasks,
    handle_pipeline_task_event,
    persist_callback_events,
    start_pipeline_run,
)
from modnews.service.pipeline.registry import PipelineRegistry
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
        return start_pipeline_run(self.step_registry, self.event_queue, request, submit=submit)

    def on_task_completed(self, event: dict[str, Any]) -> None:
        callback_events = handle_pipeline_task_event(
            self.step_registry,
            self.event_queue,
            event,
            event_type="task.completed",
        )
        persist_callback_events(event, callback_events)
        dispatch_followup_tasks(self.step_registry, self.event_queue, event, failed=False)

    def on_task_failed(self, event: dict[str, Any]) -> None:
        callback_events = handle_pipeline_task_event(
            self.step_registry,
            self.event_queue,
            event,
            event_type="task.failed",
        )
        persist_callback_events(event, callback_events)
        dispatch_followup_tasks(self.step_registry, self.event_queue, event, failed=True)

    def on_task_blocked(self, event: dict[str, Any]) -> None:
        callback_events = handle_pipeline_task_event(
            self.step_registry,
            self.event_queue,
            event,
            event_type="task.blocked",
        )
        persist_callback_events(event, callback_events)
