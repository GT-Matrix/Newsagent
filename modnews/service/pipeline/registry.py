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

    def notify(self, handler_name: str, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]]:
        callback_events: list[dict[str, Any]] = []
        for step in self.list():
            before = _queue_snapshot(queue)
            explicit: list[dict[str, Any]] | None = None
            if handler_name == "on_task_completed":
                explicit = step.on_task_completed(event, queue)
            elif handler_name == "on_task_failed":
                explicit = step.on_task_failed(event, queue)
            elif handler_name == "on_task_blocked":
                explicit = step.on_task_blocked(event, queue)
            after = _queue_snapshot(queue)
            callback_event = _build_callback_event(step.id, handler_name, event, before, after, explicit)
            if callback_event["changed_tasks"] or callback_event["decisions"]:
                callback_events.append(callback_event)
        return callback_events


def _queue_snapshot(queue: EventQueue | None) -> dict[str, dict[str, Any]]:
    if queue is None:
        return {}
    snapshot: dict[str, dict[str, Any]] = {}
    for task in queue.list():
        snapshot[task.id] = {
            "state": task.state,
            "status_reason": task.status_reason,
            "result": queue.result(task.id),
        }
    return snapshot


def _build_callback_event(
    step_id: str,
    handler_name: str,
    event: dict[str, Any],
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    explicit: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    task = event.get("task") if isinstance(event.get("task"), dict) else {}
    changed_tasks = []
    for task_id in sorted(set(before) | set(after)):
        previous = before.get(task_id)
        current = after.get(task_id)
        if previous == current:
            continue
        changed_tasks.append(
            {
                "task_id": task_id,
                "before_state": previous.get("state") if previous else None,
                "after_state": current.get("state") if current else None,
                "before_reason": previous.get("status_reason") if previous else None,
                "after_reason": current.get("status_reason") if current else None,
                "before_result": previous.get("result") if previous else {},
                "after_result": current.get("result") if current else {},
            }
        )
    return {
        "step_id": step_id,
        "handler": handler_name,
        "event_task_id": task.get("id"),
        "event_task_type": task.get("type"),
        "event_step_id": task.get("step_id"),
        "changed_tasks": changed_tasks,
        "decisions": explicit or [],
    }
