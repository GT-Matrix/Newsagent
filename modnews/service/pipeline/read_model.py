from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.runs import RunRepository
from modnews.service.pipeline.read_model_support import (
    build_domain_view,
    build_step_views,
    collect_artifacts,
    collect_callbacks,
    merge_steps,
    normalize_checkpoints,
    normalize_steps,
    status_summary,
    task_logs,
    task_summary,
)


def build_run_list_item(project_root: Path, queue: EventQueue, run_record: dict[str, Any]) -> dict[str, Any]:
    run = dict(run_record)
    run_id = str(run.get("run_id") or "")
    tasks, checkpoints, steps = _load_run_view(project_root, queue, run_id, persisted_steps=run.get("steps"))
    run["steps_summary"] = status_summary(step.get("status") for step in steps)
    run["task_summary"] = status_summary(task.state for task in tasks)
    run["active_task_ids"] = [task.id for task in tasks if task.state in {"queued", "waiting", "running"}]
    run["blocked_task_ids"] = [task.id for task in tasks if task.state == "blocked"]
    run["failed_task_ids"] = [task.id for task in tasks if task.state in {"failed", "cancelled"}]
    run["latest_checkpoint"] = checkpoints[-1] if checkpoints else None
    run["artifact_count"] = len(collect_artifacts(run, checkpoints))
    return run


def build_run_detail(project_root: Path, queue: EventQueue, run_id: str) -> dict[str, Any]:
    runs = RunRepository(project_root)
    run = dict(runs.get(run_id))
    tasks, checkpoints, steps = _load_run_view(project_root, queue, run_id, persisted_steps=run.get("steps"))
    artifacts = collect_artifacts(run, checkpoints)
    return {
        "run": run,
        "steps": steps,
        "tasks": [task_summary(queue, task, include_result=True) for task in tasks],
        "checkpoints": checkpoints,
        "artifacts": artifacts,
        "missing_task_ids": [
            task_id
            for task_id in run.get("task_ids", [])
            if isinstance(task_id, str) and task_id not in {task.id for task in tasks}
        ],
    }


def build_task_list_item(project_root: Path, queue: EventQueue, task: TaskEvent) -> dict[str, Any]:
    checkpoints = _task_checkpoints(project_root, task)
    result = queue.result(task.id)
    payload = task_summary(queue, task, include_result=False)
    payload["error"] = result.get("error")
    payload["restored_from"] = result.get("restored_from")
    payload["checkpoint_count"] = len(checkpoints)
    payload["latest_checkpoint"] = checkpoints[-1] if checkpoints else None
    payload["artifact_count"] = len(collect_artifacts(result, checkpoints))
    payload["dependent_count"] = len(queue.dependents_of(task.id))
    payload["child_count"] = len(queue.children_of(task.id))
    payload["task_group_size"] = len(queue.group_members(task.task_group_id)) if task.task_group_id else 0
    payload["domain_view"] = build_domain_view(task, result, checkpoints)
    return payload


def build_task_detail(project_root: Path, queue: EventQueue, task_id: str) -> dict[str, Any]:
    task = queue.get(task_id)
    checkpoints = _task_checkpoints(project_root, task)
    result = queue.result(task_id)
    task_payload = task_summary(queue, task, include_result=True)
    task_payload["logs"] = task_logs(project_root, task_id)
    task_payload["checkpoints"] = checkpoints
    task_payload["artifacts"] = collect_artifacts(result, checkpoints)
    task_payload["callbacks"] = collect_callbacks(result)
    task_payload["dependents"] = [
        task_summary(queue, dependent, include_result=False)
        for dependent in queue.dependents_of(task_id)
    ]
    task_payload["children"] = [
        task_summary(queue, child, include_result=False)
        for child in queue.children_of(task_id)
    ]
    task_payload["task_group_members"] = [
        task_summary(queue, member, include_result=False)
        for member in queue.group_members(task.task_group_id)
    ] if task.task_group_id else []
    task_payload["domain_view"] = build_domain_view(task, result, checkpoints)
    return task_payload


def _load_run_view(
    project_root: Path,
    queue: EventQueue,
    run_id: str,
    *,
    persisted_steps: Any,
) -> tuple[list[TaskEvent], list[dict[str, Any]], list[dict[str, Any]]]:
    checkpoints_repo = CheckpointRepository(project_root)
    tasks = [task for task in queue.list() if task.pipeline_run_id == run_id]
    checkpoints = normalize_checkpoints(
        checkpoint
        for checkpoint in checkpoints_repo.list(run_id)
        if str(checkpoint.get("run_id") or run_id) == run_id
    )
    steps = merge_steps(build_step_views(tasks, checkpoints), normalize_steps(persisted_steps))
    return tasks, checkpoints, steps


def _task_checkpoints(project_root: Path, task: TaskEvent) -> list[dict[str, Any]]:
    checkpoints_repo = CheckpointRepository(project_root)
    return normalize_checkpoints(
        checkpoint
        for checkpoint in checkpoints_repo.list(task.pipeline_run_id)
        if checkpoint.get("task_id") == task.id
    )
