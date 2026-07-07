from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import SUCCESS_STATES, TERMINAL_STATES, TaskEvent
from modnews.repository.runs import RunRepository
from modnews.service.pipeline.run_state_views import (
    build_pipeline_step_snapshots,
    build_step_snapshots,
    load_checkpoints,
    merge_pipeline_callback_events,
    restore_pipeline_descriptors,
)
from modnews.service.pipeline.step import PipelineStepDescriptor


def initialize_run_state(
    project_root: Path,
    run_id: str,
    tasks: list[TaskEvent],
    *,
    pipeline_descriptors: list[PipelineStepDescriptor] | None = None,
) -> dict[str, Any]:
    record = RunRepository(project_root).get(run_id)
    checkpoints = load_checkpoints(project_root, run_id)
    step_snapshots = build_step_snapshots(tasks, checkpoints)
    updates = {
        "task_ids": [task.id for task in tasks],
        "steps": step_snapshots,
        "pipeline_steps": build_pipeline_step_snapshots(
            step_snapshots,
            run_payload=record.get("payload"),
            descriptors=pipeline_descriptors or restore_pipeline_descriptors(record.get("pipeline_steps")),
            existing=record.get("pipeline_steps"),
        ),
    }
    return RunRepository(project_root).update(run_id, **updates)


def sync_run_state(
    project_root: Path,
    queue: EventQueue,
    run_id: str,
    *,
    override_state: str | None = None,
    extra_updates: dict[str, Any] | None = None,
    pipeline_descriptors: list[PipelineStepDescriptor] | None = None,
) -> dict[str, Any] | None:
    runs = RunRepository(project_root)
    try:
        record = runs.get(run_id)
    except KeyError:
        return None
    run_tasks = [item for item in queue.list() if item.pipeline_run_id == run_id]
    checkpoints = load_checkpoints(project_root, run_id)
    step_snapshots = build_step_snapshots(run_tasks, checkpoints, existing=record.get("steps"))
    updates = {
        "state": override_state or _derive_run_state(run_tasks, fallback=str(record.get("state") or "queued")),
        "steps": step_snapshots,
        "pipeline_steps": build_pipeline_step_snapshots(
            step_snapshots,
            run_payload=record.get("payload"),
            descriptors=pipeline_descriptors or restore_pipeline_descriptors(record.get("pipeline_steps")),
            existing=record.get("pipeline_steps"),
        ),
        "task_ids": [task.id for task in run_tasks] or list(record.get("task_ids", [])),
    }
    if extra_updates:
        updates.update(extra_updates)
    return runs.update(run_id, **updates)


def append_step_callback_events(project_root: Path, run_id: str, callback_events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not callback_events:
        return None
    runs = RunRepository(project_root)
    try:
        record = runs.get(run_id)
    except KeyError:
        return None
    existing_events = list(record.get("step_callback_events", [])) if isinstance(record.get("step_callback_events"), list) else []
    merged_events = [*existing_events, *callback_events][-200:]
    existing_steps = list(record.get("steps", [])) if isinstance(record.get("steps"), list) else []
    step_map = {
        str(step.get("step_id")): dict(step)
        for step in existing_steps
        if isinstance(step, dict) and step.get("step_id")
    }
    for callback in callback_events:
        step_id = str(callback.get("step_id") or "")
        if not step_id:
            continue
        step = step_map.setdefault(step_id, {"step_id": step_id})
        history = list(step.get("callback_events", [])) if isinstance(step.get("callback_events"), list) else []
        history.append(callback)
        step["callback_events"] = history[-50:]
    pipeline_steps = merge_pipeline_callback_events(record.get("pipeline_steps"), callback_events)
    return runs.update(
        run_id,
        step_callback_events=merged_events,
        steps=sorted(step_map.values(), key=lambda item: str(item.get("step_id") or "")),
        pipeline_steps=pipeline_steps,
    )


def update_run_state(queue: EventQueue, event: dict[str, Any], *, failed: bool = False, blocked: bool = False) -> None:
    task = event.get("task")
    result = event.get("result")
    if not isinstance(task, dict):
        return
    run_id = task.get("pipeline_run_id")
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    project_root = payload.get("project_root")
    if not run_id or not project_root:
        return
    updates: dict[str, Any] = {"state": "blocked" if blocked else "failed" if failed else "running"}
    if isinstance(result, dict):
        for key in ("checkpoint_path", "combined_ingest_path", "report_output_dir", "stats"):
            if key in result:
                updates[key] = result[key]
        if "error" in result:
            updates["error"] = result["error"]
        if "blocked_reason" in result:
            updates["blocked_reason"] = result["blocked_reason"]
    sync_run_state(Path(str(project_root)), queue, str(run_id), extra_updates=updates)


def _derive_run_state(tasks: list[TaskEvent], *, fallback: str) -> str:
    if not tasks:
        return fallback
    if any(item.state == "failed" for item in tasks):
        return "failed"
    if any(item.state == "blocked" for item in tasks):
        return "blocked"
    if any(item.state == "running" for item in tasks):
        return "running"
    if any(item.state in {"queued", "waiting"} for item in tasks):
        return "queued"
    if all(item.state in TERMINAL_STATES for item in tasks):
        return "succeeded" if all(item.state == "succeeded" for item in tasks) else "partial"
    if all(item.state in SUCCESS_STATES for item in tasks):
        return "succeeded" if all(item.state == "succeeded" for item in tasks) else "partial"
    return fallback
