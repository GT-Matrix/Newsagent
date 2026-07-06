from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.pipeline.step import PipelineStep


@dataclass(slots=True)
class PipelineRegistry:
    steps: dict[str, PipelineStep] = field(default_factory=dict)

    def register(self, step: PipelineStep) -> None:
        self.steps[step.id] = step

    def list(self) -> list[PipelineStep]:
        return list(self.steps.values())

    def plan_run(self, state: dict[str, Any]) -> list[TaskEvent]:
        tasks: list[TaskEvent] = []
        for step in self.list():
            tasks.extend(step.plan({**state, "tasks": tasks}))
        return tasks

    def plan_followup(self, completed_event: dict[str, Any]) -> list[TaskEvent]:
        tasks: list[TaskEvent] = []
        for step in self.list():
            tasks.extend(step.plan({}, completed_event=completed_event))
        return tasks

    def notify(self, handler_name: str, event: dict[str, Any], queue: EventQueue | None) -> None:
        for step in self.list():
            handler = getattr(step, handler_name, None)
            if not callable(handler):
                continue
            if len(inspect.signature(handler).parameters) >= 2:
                handler(event, queue)
            else:
                handler(event)
