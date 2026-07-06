from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.pipeline.registry_support import (
    notify_steps,
    plan_followup_tasks,
    plan_run_tasks,
)
from modnews.service.pipeline.step import PipelinePlanContext, PipelineStep


@dataclass(slots=True)
class PipelineRegistry:
    steps: dict[str, PipelineStep] = field(default_factory=dict)

    def register(self, step: PipelineStep) -> None:
        self.steps[step.id] = step

    def list(self) -> list[PipelineStep]:
        return list(self.steps.values())

    def plan_run(self, context: PipelinePlanContext) -> list[TaskEvent]:
        return plan_run_tasks(self.list(), context)

    def plan_followup(self, completed_event: dict[str, Any]) -> list[TaskEvent]:
        return plan_followup_tasks(self.list(), completed_event)

    def notify(self, handler_name: str, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]]:
        return notify_steps(self.list(), handler_name, event, queue)
