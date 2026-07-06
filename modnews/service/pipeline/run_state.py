from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import SUCCESS_STATES, TERMINAL_STATES, TaskEvent
from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.runs import RunRepository


def initialize_run_state(project_root: Path, run_id: str, tasks: list[TaskEvent]) -> dict[str, Any]:
    record = RunRepository(project_root).get(run_id)
    updates = {
        "task_ids": [task.id for task in tasks],
        "steps": _build_step_snapshots(tasks, _load_checkpoints(project_root, run_id)),
    }
    return RunRepository(project_root).update(run_id, **updates)


def sync_run_state(
    project_root: Path,
    queue: EventQueue,
    run_id: str,
    *,
    override_state: str | None = None,
    extra_updates: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    runs = RunRepository(project_root)
    try:
        record = runs.get(run_id)
    except KeyError:
        return None
    run_tasks = [item for item in queue.list() if item.pipeline_run_id == run_id]
    checkpoints = _load_checkpoints(project_root, run_id)
    updates = {
        "state": override_state or _derive_run_state(run_tasks, fallback=str(record.get("state") or "queued")),
        "steps": _build_step_snapshots(run_tasks, checkpoints, existing=record.get("steps")),
        "task_ids": [task.id for task in run_tasks] or list(record.get("task_ids", [])),
    }
    if extra_updates:
        updates.update(extra_updates)
    return runs.update(run_id, **updates)


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
