from __future__ import annotations

from typing import Any, Protocol

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent


class PipelineStep(Protocol):
    id: str

    def plan(self, state: dict[str, Any], completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        ...

    def on_task_completed(self, event: dict[str, Any], queue: EventQueue | None) -> None:
        ...

    def on_task_failed(self, event: dict[str, Any], queue: EventQueue | None) -> None:
        ...

    def on_task_blocked(self, event: dict[str, Any], queue: EventQueue) -> None:
        ...
