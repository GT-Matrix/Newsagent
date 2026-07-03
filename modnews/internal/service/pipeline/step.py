from __future__ import annotations

from typing import Any, Protocol

from modnews.core.task import TaskEvent


class PipelineStep(Protocol):
    id: str

    def plan(self, state: dict[str, Any], completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        ...
