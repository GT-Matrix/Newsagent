from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.service.pipeline.event_runtime import PipelineEventRuntime
from modnews.service.pipeline.manager_support import start_pipeline_run
from modnews.service.pipeline.registry import PipelineRegistry
from modnews.service.pipeline.step import PipelineStep, PipelineStepDescriptor


@dataclass(slots=True)
class PipelineManager:
    step_registry: PipelineRegistry = field(default_factory=PipelineRegistry)
    event_queue: EventQueue | None = None
    event_router: EventRouter | None = None
    ingest_registry: Any | None = None

    @property
    def steps(self) -> list[PipelineStep]:
        return self.step_registry.list()

    def describe_steps(self) -> list[PipelineStepDescriptor]:
        return self.step_registry.describe()

    def bind(self, event_queue: EventQueue, event_router: EventRouter) -> None:
        self.event_queue = event_queue
        self.event_router = event_router

    def register_step(self, step: PipelineStep) -> None:
        self.step_registry.register(step)

    def _event_runtime(self) -> PipelineEventRuntime:
        return PipelineEventRuntime(self.step_registry, self.event_queue)

    def start_run(self, request: dict[str, Any], *, submit: bool = False) -> dict[str, Any]:
        return start_pipeline_run(self.step_registry, self.event_queue, request, submit=submit)

    def on_task_completed(self, event: dict[str, Any]) -> None:
        self._event_runtime().handle(event, event_type="task.completed")

    def on_task_failed(self, event: dict[str, Any]) -> None:
        self._event_runtime().handle(event, event_type="task.failed")

    def on_task_blocked(self, event: dict[str, Any]) -> None:
        self._event_runtime().handle(event, event_type="task.blocked")
