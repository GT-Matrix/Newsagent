from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import SUCCESS_STATES, TERMINAL_STATES, TaskEvent
from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.runs import RunRepository
from modnews.service.pipeline.read_model_support import build_pipeline_step_views, pipeline_status_overrides
from modnews.service.pipeline.step import PipelineFollowupDescriptor, PipelineStepDescriptor


def initialize_run_state(
    project_root: Path,
    run_id: str,
    tasks: list[TaskEvent],
    *,
    pipeline_descriptors: list[PipelineStepDescriptor] | None = None,
) -> dict[str, Any]:
    record = RunRepository(project_root).get(run_id)
    checkpoints = _load_checkpoints(project_root, run_id)
    step_snapshots = _build_step_snapshots(tasks, checkpoints)
    updates = {
        "task_ids": [task.id for task in tasks],
        "steps": step_snapshots,
        "pipeline_steps": _build_pipeline_step_snapshots(
            step_snapshots,
            run_payload=record.get("payload"),
            descriptors=pipeline_descriptors or _restore_pipeline_descriptors(record.get("pipeline_steps")),
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
    checkpoints = _load_checkpoints(project_root, run_id)
    step_snapshots = _build_step_snapshots(run_tasks, checkpoints, existing=record.get("steps"))
    updates = {
        "state": override_state or _derive_run_state(run_tasks, fallback=str(record.get("state") or "queued")),
        "steps": step_snapshots,
        "pipeline_steps": _build_pipeline_step_snapshots(
            step_snapshots,
            run_payload=record.get("payload"),
            descriptors=pipeline_descriptors or _restore_pipeline_descriptors(record.get("pipeline_steps")),
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
    pipeline_steps = _merge_pipeline_callback_events(record.get("pipeline_steps"), callback_events)
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


def _build_step_snapshots(
    tasks: list[TaskEvent],
    checkpoints: list[dict[str, Any]],
    *,
    existing: Any = None,
) -> list[dict[str, Any]]:
    grouped_tasks: dict[str, list[TaskEvent]] = defaultdict(list)
    for task in tasks:
        grouped_tasks[str(task.step_id or "unassigned")].append(task)

    grouped_checkpoints: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for checkpoint in checkpoints:
        grouped_checkpoints[str(checkpoint.get("step_id") or "unassigned")].append(checkpoint)

    existing_by_step = {
        str(item.get("step_id")): item
        for item in existing
        if isinstance(item, dict) and item.get("step_id")
    } if isinstance(existing, list) else {}
    step_ids = sorted(set(grouped_tasks) | set(grouped_checkpoints) | set(existing_by_step))
    task_step_by_id = {task.id: str(task.step_id or "unassigned") for task in tasks}
    snapshots = []
    for step_id in step_ids:
        step_tasks = grouped_tasks.get(step_id, [])
        step_checkpoints = grouped_checkpoints.get(step_id, [])
        previous = existing_by_step.get(step_id, {})
        latest_checkpoint = step_checkpoints[-1] if step_checkpoints else previous.get("latest_checkpoint")
        depends_on = sorted(
            {
                task_step_by_id[dependency_id]
                for task in step_tasks
                for dependency_id in task.depends_on
                if dependency_id in task_step_by_id and task_step_by_id[dependency_id] != step_id
            }
        ) or list(previous.get("depends_on", []))
        snapshot = {
            "step_id": step_id,
            "status": _derive_step_state(step_tasks, step_checkpoints, fallback=str(previous.get("status") or "idle")),
            "depends_on": depends_on,
            "task_ids": [task.id for task in step_tasks] or list(previous.get("task_ids", [])),
            "queued_task_ids": [task.id for task in step_tasks if task.state in {"queued", "waiting", "running"}],
            "completed_task_ids": [task.id for task in step_tasks if task.state in SUCCESS_STATES],
            "blocked_task_ids": [task.id for task in step_tasks if task.state == "blocked"],
            "skipped_task_ids": [task.id for task in step_tasks if task.state == "skipped"],
            "failed_task_ids": [task.id for task in step_tasks if task.state in {"failed", "cancelled"}],
            "latest_checkpoint": latest_checkpoint,
            "checkpoint_count": len(step_checkpoints) or int(previous.get("checkpoint_count", 0)),
            "artifacts": _checkpoint_artifacts(latest_checkpoint),
            "stats": latest_checkpoint.get("stats", {}) if isinstance(latest_checkpoint, dict) else dict(previous.get("stats", {})),
            "callback_events": list(previous.get("callback_events", [])) if isinstance(previous.get("callback_events"), list) else [],
        }
        snapshots.append(snapshot)
    return snapshots


def _derive_step_state(tasks: list[TaskEvent], checkpoints: list[dict[str, Any]], *, fallback: str) -> str:
    if tasks:
        states = {task.state for task in tasks}
        if "failed" in states:
            return "failed"
        if "blocked" in states:
            return "blocked"
        if "running" in states:
            return "running"
        if states & {"queued", "waiting"}:
            return "queued"
        if states and states <= SUCCESS_STATES:
            return "succeeded" if states == {"succeeded"} else "partial"
        if states and all(state in TERMINAL_STATES for state in states):
            return "partial"
    if checkpoints:
        status = checkpoints[-1].get("status")
        if status:
            return str(status)
    return fallback


def _checkpoint_artifacts(checkpoint: Any) -> list[dict[str, Any]]:
    if not isinstance(checkpoint, dict):
        return []
    refs = checkpoint.get("output_refs")
    if not isinstance(refs, dict):
        return []
    artifacts = []
    for name, value in refs.items():
        if not value:
            continue
        path = Path(str(value)).expanduser().resolve()
        artifacts.append({"name": str(name), "role": "output", "path": str(path), "exists": path.exists(), "is_dir": path.is_dir() if path.exists() else False})
    return sorted(artifacts, key=lambda item: item["name"])


def _load_checkpoints(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    return [
        checkpoint
        for checkpoint in CheckpointRepository(project_root).list(run_id)
        if str(checkpoint.get("run_id") or run_id) == run_id
    ]


def _build_pipeline_step_snapshots(
    step_snapshots: list[dict[str, Any]],
    *,
    run_payload: Any,
    descriptors: list[PipelineStepDescriptor],
    existing: Any = None,
) -> list[dict[str, Any]]:
    if not descriptors:
        return list(existing) if isinstance(existing, list) else []
    pipeline_steps = build_pipeline_step_views(
        descriptors,
        step_snapshots,
        status_overrides=pipeline_status_overrides(run_payload),
    )
    existing_by_step = {
        str(item.get("step_id")): item
        for item in existing
        if isinstance(item, dict) and item.get("step_id")
    } if isinstance(existing, list) else {}
    for step in pipeline_steps:
        previous = existing_by_step.get(str(step.get("step_id") or ""), {})
        if step.get("callback_events"):
            continue
        if isinstance(previous.get("callback_events"), list):
            step["callback_events"] = list(previous.get("callback_events", []))
    return pipeline_steps


def _restore_pipeline_descriptors(value: Any) -> list[PipelineStepDescriptor]:
    if not isinstance(value, list):
        return []
    rows: list[PipelineStepDescriptor] = []
    for item in value:
        if not isinstance(item, dict) or not item.get("step_id"):
            continue
        followups = []
        for followup in item.get("followups", []):
            if not isinstance(followup, dict):
                continue
            followups.append(
                PipelineFollowupDescriptor(
                    trigger=str(followup.get("trigger") or ""),
                    builder_id=str(followup.get("builder_id") or ""),
                    task_type=str(followup["task_type"]) if followup.get("task_type") is not None else None,
                    step_prefix=str(followup["step_prefix"]) if followup.get("step_prefix") is not None else None,
                )
            )
        rows.append(
            PipelineStepDescriptor(
                step_id=str(item.get("step_id") or ""),
                title=str(item.get("title") or item.get("step_id") or ""),
                group=str(item.get("group") or "pipeline"),
                kind=str(item.get("kind") or "root"),
                description=str(item["description"]) if item.get("description") is not None else None,
                depends_on=tuple(str(dep) for dep in item.get("depends_on", []) if dep),
                callback_handlers=tuple(str(handler) for handler in item.get("callback_handlers", []) if handler),
                followups=tuple(followups),
                concrete_step_ids=tuple(str(step_id) for step_id in item.get("concrete_step_ids", []) if step_id),
                concrete_step_prefixes=tuple(str(prefix) for prefix in item.get("concrete_step_prefixes", []) if prefix),
            )
        )
    return rows


def _merge_pipeline_callback_events(existing: Any, callback_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    step_map = {
        str(step.get("step_id")): dict(step)
        for step in existing
        if isinstance(step, dict) and step.get("step_id")
    } if isinstance(existing, list) else {}
    for callback in callback_events:
        step_id = str(callback.get("step_id") or "")
        if not step_id:
            continue
        step = step_map.setdefault(step_id, {"step_id": step_id})
        history = list(step.get("callback_events", [])) if isinstance(step.get("callback_events"), list) else []
        history.append(callback)
        step["callback_events"] = history[-50:]
    return sorted(step_map.values(), key=lambda item: str(item.get("step_id") or ""))
