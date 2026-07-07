from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.runs import RunRepository
from modnews.service.pipeline.read_model_support import (
    attach_checkpoint_callback_summaries,
    build_attempt_history,
    build_domain_view,
    build_pipeline_step_views,
    build_step_views,
    collect_artifacts,
    collect_callbacks,
    merge_steps,
    normalize_checkpoints,
    normalize_steps,
    pipeline_status_overrides,
    related_checkpoint_path,
    status_summary,
    task_display_summary,
    task_logs,
    task_summary,
)
from modnews.service.pipeline.runtime_store import overlay_run_record
from modnews.service.pipeline.step import PipelineStepDescriptor


def build_run_list_item(
    project_root: Path,
    queue: EventQueue,
    run_record: dict[str, Any],
    *,
    pipeline_descriptors: list[PipelineStepDescriptor] | None = None,
) -> dict[str, Any]:
    run = overlay_run_record(project_root, dict(run_record))
    run_id = str(run.get("run_id") or "")
    tasks, checkpoints, steps, pipeline_steps = _load_run_view(
        project_root,
        queue,
        run_id,
        run_payload=run.get("payload"),
        persisted_steps=run.get("steps"),
        pipeline_descriptors=pipeline_descriptors,
    )
    run["steps_summary"] = status_summary(step.get("status") for step in steps)
    run["pipeline_steps_summary"] = status_summary(step.get("status") for step in pipeline_steps)
    run["task_summary"] = status_summary(task.state for task in tasks)
    run["active_task_ids"] = [task.id for task in tasks if task.state in {"queued", "waiting", "running"}]
    run["blocked_task_ids"] = [task.id for task in tasks if task.state == "blocked"]
    run["failed_task_ids"] = [task.id for task in tasks if task.state in {"failed", "cancelled"}]
    run["latest_checkpoint"] = checkpoints[-1] if checkpoints else None
    run["artifact_count"] = len(collect_artifacts(run, checkpoints))
    run["state"] = _resolve_run_state(run, tasks, steps, pipeline_steps)
    return run


def build_run_detail(
    project_root: Path,
    queue: EventQueue,
    run_id: str,
    *,
    pipeline_descriptors: list[PipelineStepDescriptor] | None = None,
) -> dict[str, Any]:
    runs = RunRepository(project_root)
    run = overlay_run_record(project_root, dict(runs.get(run_id)))
    tasks, checkpoints, steps, pipeline_steps = _load_run_view(
        project_root,
        queue,
        run_id,
        run_payload=run.get("payload"),
        persisted_steps=run.get("steps"),
        pipeline_descriptors=pipeline_descriptors,
    )
    artifacts = collect_artifacts(run, checkpoints)
    run["steps_summary"] = status_summary(step.get("status") for step in steps)
    run["pipeline_steps_summary"] = status_summary(step.get("status") for step in pipeline_steps)
    run["task_summary"] = status_summary(task.state for task in tasks)
    run["active_task_ids"] = [task.id for task in tasks if task.state in {"queued", "waiting", "running"}]
    run["blocked_task_ids"] = [task.id for task in tasks if task.state == "blocked"]
    run["failed_task_ids"] = [task.id for task in tasks if task.state in {"failed", "cancelled"}]
    run["latest_checkpoint"] = checkpoints[-1] if checkpoints else None
    run["artifact_count"] = len(artifacts)
    run["state"] = _resolve_run_state(run, tasks, steps, pipeline_steps)
    return {
        "run": run,
        "steps": steps,
        "pipeline_steps": pipeline_steps,
        "tasks": _task_summaries(queue, tasks, include_result=True),
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
    inspection = queue.inspect_tasks([task]).get(task.id, {})
    result = inspection.get("result") if isinstance(inspection.get("result"), dict) else queue.result(task.id)
    payload = task_summary(queue, task, include_result=False, inspection=inspection)
    payload["error"] = result.get("error")
    payload["restored_from"] = result.get("restored_from")
    payload["summary"] = task_display_summary(
        task,
        result,
        blocked_reason=payload.get("blocked_reason"),
        waiting_reason=payload.get("waiting_reason"),
        checkpoint_path=related_checkpoint_path(result, checkpoints),
    )
    payload["checkpoint_count"] = len(checkpoints)
    payload["latest_checkpoint"] = checkpoints[-1] if checkpoints else None
    payload["artifact_count"] = len(collect_artifacts(result, checkpoints))
    payload["dependent_count"] = len(queue.dependents_of(task.id))
    payload["child_count"] = len(queue.children_of(task.id))
    payload["task_group_size"] = len(queue.group_members(task.task_group_id)) if task.task_group_id else 0
    payload["task_group_summary"] = queue.group_summary(task.task_group_id) if task.task_group_id else None
    payload["domain_view"] = build_domain_view(task, result, checkpoints)
    payload["related_checkpoint_path"] = related_checkpoint_path(result, checkpoints)
    payload["related_artifacts"] = collect_artifacts(result, checkpoints)
    return payload


def build_task_detail(project_root: Path, queue: EventQueue, task_id: str) -> dict[str, Any]:
    task = queue.get(task_id)
    checkpoints = _task_checkpoints(project_root, task)
    inspection = queue.inspect_tasks([task]).get(task.id, {})
    result = inspection.get("result") if isinstance(inspection.get("result"), dict) else queue.result(task_id)
    task_payload = task_summary(queue, task, include_result=True, inspection=inspection)
    task_payload["logs"] = task_logs(project_root, task_id)
    task_payload["attempt_history"] = build_attempt_history(task_payload["logs"])
    task_payload["checkpoints"] = checkpoints
    task_payload["artifacts"] = collect_artifacts(result, checkpoints)
    task_payload["summary"] = task_display_summary(
        task,
        result,
        blocked_reason=task_payload.get("blocked_reason"),
        waiting_reason=task_payload.get("waiting_reason"),
        checkpoint_path=related_checkpoint_path(result, checkpoints),
    )
    task_payload["callbacks"] = collect_callbacks(result)
    dependents = queue.dependents_of(task_id)
    children = queue.children_of(task_id)
    members = queue.group_members(task.task_group_id) if task.task_group_id else []
    related_tasks = [*dependents, *children, *members]
    related_inspections = queue.inspect_tasks(related_tasks) if related_tasks else {}
    task_payload["dependents"] = [
        task_summary(queue, dependent, include_result=False, inspection=related_inspections.get(dependent.id, {}))
        for dependent in dependents
    ]
    task_payload["children"] = [
        task_summary(queue, child, include_result=False, inspection=related_inspections.get(child.id, {}))
        for child in children
    ]
    task_payload["task_group_members"] = [
        task_summary(queue, member, include_result=False, inspection=related_inspections.get(member.id, {}))
        for member in members
    ]
    task_payload["task_group_summary"] = queue.group_summary(task.task_group_id) if task.task_group_id else None
    task_payload["domain_view"] = build_domain_view(task, result, checkpoints)
    task_payload["related_checkpoint_path"] = related_checkpoint_path(result, checkpoints)
    task_payload["related_artifacts"] = collect_artifacts(result, checkpoints)
    return task_payload


def _load_run_view(
    project_root: Path,
    queue: EventQueue,
    run_id: str,
    *,
    run_payload: Any,
    persisted_steps: Any,
    pipeline_descriptors: list[PipelineStepDescriptor] | None,
) -> tuple[list[TaskEvent], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    checkpoints_repo = CheckpointRepository(project_root)
    tasks = queue.list_by_run(run_id)
    checkpoints = normalize_checkpoints(
        checkpoint
        for checkpoint in checkpoints_repo.list(run_id)
        if str(checkpoint.get("run_id") or run_id) == run_id
    )
    checkpoints = attach_checkpoint_callback_summaries(project_root, checkpoints)
    steps = merge_steps(build_step_views(tasks, checkpoints), normalize_steps(persisted_steps))
    pipeline_steps = build_pipeline_step_views(
        pipeline_descriptors or [],
        steps,
        status_overrides=pipeline_status_overrides(run_payload),
    )
    return tasks, checkpoints, steps, pipeline_steps


def _task_summaries(queue: EventQueue, tasks: list[TaskEvent], *, include_result: bool) -> list[dict[str, Any]]:
    inspections = queue.inspect_tasks(tasks)
    return [
        task_summary(queue, task, include_result=include_result, inspection=inspections.get(task.id, {}))
        for task in tasks
    ]


def _task_checkpoints(project_root: Path, task: TaskEvent) -> list[dict[str, Any]]:
    checkpoints_repo = CheckpointRepository(project_root)
    return attach_checkpoint_callback_summaries(
        project_root,
        normalize_checkpoints(
        checkpoint
        for checkpoint in checkpoints_repo.list(task.pipeline_run_id)
        if checkpoint.get("task_id") == task.id
        ),
    )


def _resolve_run_state(
    run: dict[str, Any],
    tasks: list[TaskEvent],
    steps: list[dict[str, Any]],
    pipeline_steps: list[dict[str, Any]],
) -> str:
    if tasks:
        if any(task.state == "failed" for task in tasks):
            return "failed"
        if any(task.state == "blocked" for task in tasks):
            return "blocked"
        if any(task.state == "running" for task in tasks):
            return "running"
        if any(task.state in {"queued", "waiting"} for task in tasks):
            return "queued"
        if all(task.state == "succeeded" for task in tasks):
            return "succeeded"
        if all(task.state in {"succeeded", "skipped"} for task in tasks):
            return "partial"
    concrete_statuses = [str(step.get("status") or "") for step in steps if step.get("status")]
    pipeline_statuses = [str(step.get("status") or "") for step in pipeline_steps if step.get("status")]
    statuses = concrete_statuses or pipeline_statuses
    if statuses:
        if "failed" in statuses:
            return "failed"
        if "blocked" in statuses:
            return "blocked"
        if "running" in statuses:
            return "running"
        if "queued" in statuses:
            return "queued"
        material = [status for status in statuses if status != "idle"]
        if material and all(status == "succeeded" for status in material):
            return "succeeded"
        if any(status == "partial" for status in material):
            return "partial"
    return str(run.get("state") or "queued")
