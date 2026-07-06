from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.core.task import TaskEvent
from modnews.service.pipeline.registry import PipelineRegistry
from modnews.service.pipeline.run_state import append_step_callback_events, update_run_state
from modnews.service.pipeline.step import PipelinePlanContext


def start_pipeline_run(
    registry: PipelineRegistry,
    event_queue: EventQueue | None,
    request: dict[str, Any],
    *,
    submit: bool,
) -> dict[str, Any]:
    run_id = str(request.get("run_id") or "local")
    tasks = registry.plan_run(PipelinePlanContext(run_id=run_id, request=request))
    if event_queue:
        for task in tasks:
            if submit:
                event_queue.submit(task)
            else:
                event_queue.register(task)
    return {"run_id": run_id, "registered_tasks": [task.to_dict() for task in tasks]}


def handle_pipeline_task_event(
    registry: PipelineRegistry,
    event_queue: EventQueue | None,
    event: dict[str, Any],
    *,
    event_type: str,
) -> list[dict[str, Any]]:
    if event_queue is None:
        return []
    if event_type == "task.completed":
        update_run_state(event_queue, event)
        callback_events = registry.notify("on_task_completed", event, event_queue)
        if callback_events:
            update_run_state(event_queue, event)
        return callback_events
    if event_type == "task.failed":
        update_run_state(event_queue, event, failed=True)
        callback_events = registry.notify("on_task_failed", event, event_queue)
        if callback_events:
            update_run_state(event_queue, event, failed=True)
        return callback_events
    if event_type == "task.blocked":
        update_run_state(event_queue, event, blocked=True)
        callback_events = registry.notify("on_task_blocked", event, event_queue)
        if callback_events:
            update_run_state(event_queue, event, blocked=True)
        return callback_events
    return []


def dispatch_followup_tasks(
    registry: PipelineRegistry,
    event_queue: EventQueue | None,
    event: dict[str, Any],
    *,
    failed: bool,
) -> None:
    if failed or event_queue is None:
        return
    for task in registry.plan_followup(event):
        event_queue.submit(task)


def persist_callback_events(event: dict[str, Any], callback_events: list[dict[str, Any]]) -> None:
    task = event.get("task")
    if not isinstance(task, dict):
        return
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    project_root = payload.get("project_root")
    run_id = task.get("pipeline_run_id")
    if not project_root or not run_id:
        return
    append_step_callback_events(Path(str(project_root)), str(run_id), callback_events)
