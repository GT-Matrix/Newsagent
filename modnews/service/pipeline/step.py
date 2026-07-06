from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent


@dataclass(slots=True)
class PipelinePlanContext:
    run_id: str
    request: dict[str, Any]
    tasks: list[TaskEvent] = field(default_factory=list)


class PipelineStep(Protocol):
    id: str

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        ...

    def on_task_completed(self, event: dict[str, Any], queue: EventQueue | None) -> None:
        ...

    def on_task_failed(self, event: dict[str, Any], queue: EventQueue | None) -> None:
        ...

    def on_task_blocked(self, event: dict[str, Any], queue: EventQueue) -> None:
        ...


class PipelineStepBase:
    id: str

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        raise NotImplementedError

    def on_task_completed(self, event: dict[str, Any], queue: EventQueue | None) -> None:
        return None

    def on_task_failed(self, event: dict[str, Any], queue: EventQueue | None) -> None:
        return None

    def on_task_blocked(self, event: dict[str, Any], queue: EventQueue | None) -> None:
        return None
