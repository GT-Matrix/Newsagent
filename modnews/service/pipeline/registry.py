from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.pipeline.step import PipelinePlanContext, PipelineStep


@dataclass(slots=True)
class PipelineRegistry:
    steps: dict[str, PipelineStep] = field(default_factory=dict)

    def register(self, step: PipelineStep) -> None:
        self.steps[step.id] = step

    def list(self) -> list[PipelineStep]:
        return list(self.steps.values())

    def plan_run(self, context: PipelinePlanContext) -> list[TaskEvent]:
        tasks = list(context.tasks)
        for step in self.list():
            tasks.extend(step.plan(PipelinePlanContext(run_id=context.run_id, request=context.request, tasks=tasks)))
        return tasks

    def plan_followup(self, completed_event: dict[str, Any]) -> list[TaskEvent]:
        tasks: list[TaskEvent] = []
        for step in self.list():
            tasks.extend(step.plan(PipelinePlanContext(run_id="", request={}, tasks=[]), completed_event=completed_event))
        return tasks

    def notify(self, handler_name: str, event: dict[str, Any], queue: EventQueue | None) -> None:
        for step in self.list():
            if handler_name == "on_task_completed":
                step.on_task_completed(event, queue)
            elif handler_name == "on_task_failed":
                step.on_task_failed(event, queue)
            elif handler_name == "on_task_blocked":
                step.on_task_blocked(event, queue)
