from __future__ import annotations

from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.pipeline.step import PipelinePlanContext, PipelineStep


def plan_run_tasks(steps: list[PipelineStep], context: PipelinePlanContext) -> list[TaskEvent]:
    tasks = list(context.tasks)
    for step in steps:
        tasks.extend(step.plan(PipelinePlanContext(run_id=context.run_id, request=context.request, tasks=tasks)))
    return tasks


def plan_followup_tasks(steps: list[PipelineStep], completed_event: dict[str, Any]) -> list[TaskEvent]:
    tasks: list[TaskEvent] = []
    for step in steps:
        tasks.extend(step.plan(PipelinePlanContext(run_id="", request={}, tasks=[]), completed_event=completed_event))
    return tasks


def notify_steps(
    steps: list[PipelineStep],
    handler_name: str,
    event: dict[str, Any],
    queue: EventQueue | None,
) -> list[dict[str, Any]]:
    callback_events: list[dict[str, Any]] = []
    for step in steps:
        explicit: list[dict[str, Any]] | None = None
        if handler_name == "on_task_completed":
            explicit = step.on_task_completed(event, queue)
        elif handler_name == "on_task_failed":
            explicit = step.on_task_failed(event, queue)
        elif handler_name == "on_task_blocked":
            explicit = step.on_task_blocked(event, queue)
        callback_event = build_callback_event(step.id, handler_name, event, explicit)
        if callback_event["decisions"] or callback_event["changed_tasks"]:
            callback_events.append(callback_event)
    return callback_events


def build_callback_event(
    step_id: str,
    handler_name: str,
    event: dict[str, Any],
    explicit: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    task = event.get("task") if isinstance(event.get("task"), dict) else {}
    decisions = list(explicit or [])
    changed_tasks = []
    for decision in decisions:
        if not isinstance(decision, dict) or not isinstance(decision.get("changed_tasks"), list):
            continue
        changed_tasks.extend(dict(change) for change in decision["changed_tasks"] if isinstance(change, dict))
    return {
        "step_id": step_id,
        "handler": handler_name,
        "event_task_id": task.get("id"),
        "event_task_type": task.get("type"),
        "event_step_id": task.get("step_id"),
        "changed_tasks": changed_tasks,
        "decisions": decisions,
    }
