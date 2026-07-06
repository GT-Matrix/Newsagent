from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import SUCCESS_STATES, TERMINAL_STATES, TaskEvent


def build_step_views(tasks: list[TaskEvent], checkpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped_tasks: dict[str, list[TaskEvent]] = defaultdict(list)
    for task in tasks:
        grouped_tasks[str(task.step_id or "unassigned")].append(task)

    grouped_checkpoints: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for checkpoint in checkpoints:
        grouped_checkpoints[str(checkpoint.get("step_id") or "unassigned")].append(checkpoint)

    step_ids = sorted(set(grouped_tasks) | set(grouped_checkpoints))
    task_step_by_id = {task.id: str(task.step_id or "unassigned") for task in tasks}
    step_views = []
    for step_id in step_ids:
        step_tasks = grouped_tasks.get(step_id, [])
        step_checkpoints = grouped_checkpoints.get(step_id, [])
        depends_on = sorted(
            {
                task_step_by_id[dependency_id]
                for task in step_tasks
                for dependency_id in task.depends_on
                if dependency_id in task_step_by_id and task_step_by_id[dependency_id] != step_id
            }
        )
        latest_checkpoint = step_checkpoints[-1] if step_checkpoints else None
        step_views.append(
            {
                "step_id": step_id,
                "status": step_status(step_tasks, step_checkpoints),
                "depends_on": depends_on,
                "task_ids": [task.id for task in step_tasks],
                "queued_task_ids": [task.id for task in step_tasks if task.state in {"queued", "waiting", "running"}],
                "completed_task_ids": [task.id for task in step_tasks if task.state in SUCCESS_STATES],
                "blocked_task_ids": [task.id for task in step_tasks if task.state == "blocked"],
                "skipped_task_ids": [task.id for task in step_tasks if task.state == "skipped"],
                "failed_task_ids": [task.id for task in step_tasks if task.state in {"failed", "cancelled"}],
                "latest_checkpoint": latest_checkpoint,
                "checkpoint_count": len(step_checkpoints),
                "artifacts": checkpoint_artifacts(latest_checkpoint) if latest_checkpoint else [],
                "stats": latest_checkpoint.get("stats", {}) if latest_checkpoint else {},
            }
        )
    return step_views


def step_status(tasks: list[TaskEvent], checkpoints: list[dict[str, Any]]) -> str:
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
        latest = checkpoints[-1]
        status = latest.get("status")
        if status:
            return str(status)
    return "idle"


def task_summary(queue: EventQueue, task: TaskEvent, *, include_result: bool) -> dict[str, Any]:
    payload = task.to_dict()
    waiting_reason = queue.waiting_reason(task)
    waiting_details = queue.waiting_details(task)
    blocked_reason = queue.blocked_reason(task)
    blocked_details = queue.blocked_details(task)
    result = queue.result(task.id)
    if waiting_reason:
        payload["waiting_reason"] = waiting_reason
    if waiting_details:
        payload["waiting_details"] = waiting_details
    if blocked_reason:
        payload["blocked_reason"] = blocked_reason
    if blocked_details:
        payload["blocked_details"] = blocked_details
    if result.get("retry_scheduled") is not None:
        payload["retry_scheduled"] = bool(result.get("retry_scheduled"))
    if result.get("retry_delay_seconds") is not None:
        payload["retry_delay_seconds"] = result.get("retry_delay_seconds")
    if result.get("next_attempt_at") is not None:
        payload["scheduled_next_attempt_at"] = result.get("next_attempt_at")
    payload["ready"] = waiting_details is None and task.state in {"queued", "waiting"}
    if include_result:
        payload["result"] = result
    return payload


def normalize_checkpoints(checkpoints: Any) -> list[dict[str, Any]]:
    rows = []
    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict):
            continue
        row = dict(checkpoint)
        row["input_artifacts"] = artifact_refs(row.get("input_refs"), role="input")
        row["output_artifacts"] = artifact_refs(row.get("output_refs"), role="output")
        rows.append(row)
    return sorted(rows, key=lambda row: str(row.get("finished_at") or row.get("started_at") or row.get("path") or ""))


def normalize_steps(steps: Any) -> list[dict[str, Any]]:
    if not isinstance(steps, list):
        return []
    rows = []
    for step in steps:
        if not isinstance(step, dict) or not step.get("step_id"):
            continue
        row = dict(step)
        latest_checkpoint = row.get("latest_checkpoint")
        if isinstance(latest_checkpoint, dict):
            row["latest_checkpoint"] = normalize_checkpoints([latest_checkpoint])[0]
        row["artifacts"] = [
            artifact
            for artifact in row.get("artifacts", [])
            if isinstance(artifact, dict) and artifact.get("path")
        ]
        row["callback_events"] = [
            event
            for event in row.get("callback_events", [])
            if isinstance(event, dict) and event.get("handler")
        ]
        rows.append(row)
    return sorted(rows, key=lambda row: str(row.get("step_id") or ""))


def merge_steps(current: list[dict[str, Any]], persisted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not persisted:
        return current
    merged = {str(step.get("step_id")): dict(step) for step in persisted if step.get("step_id")}
    for step in current:
        step_id = str(step.get("step_id") or "")
        if not step_id:
            continue
        base = merged.get(step_id, {})
        merged[step_id] = {
            **base,
            **step,
            "task_ids": step.get("task_ids") or base.get("task_ids", []),
            "queued_task_ids": step.get("queued_task_ids") or base.get("queued_task_ids", []),
            "completed_task_ids": step.get("completed_task_ids") or base.get("completed_task_ids", []),
            "blocked_task_ids": step.get("blocked_task_ids") or base.get("blocked_task_ids", []),
            "skipped_task_ids": step.get("skipped_task_ids") or base.get("skipped_task_ids", []),
            "failed_task_ids": step.get("failed_task_ids") or base.get("failed_task_ids", []),
            "artifacts": step.get("artifacts") or base.get("artifacts", []),
            "stats": step.get("stats") or base.get("stats", {}),
            "latest_checkpoint": step.get("latest_checkpoint") or base.get("latest_checkpoint"),
            "depends_on": step.get("depends_on") or base.get("depends_on", []),
        }
    return sorted(merged.values(), key=lambda row: str(row.get("step_id") or ""))


def collect_artifacts(source: dict[str, Any], checkpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts: dict[tuple[str, str], dict[str, Any]] = {}
    for checkpoint in checkpoints:
        for artifact in checkpoint.get("input_artifacts", []):
            artifacts[(artifact["role"], artifact["path"])] = artifact
        for artifact in checkpoint.get("output_artifacts", []):
            artifacts[(artifact["role"], artifact["path"])] = artifact
    for key in ("combined_ingest_path", "checkpoint_path"):
        value = source.get(key)
        if isinstance(value, str) and value:
            info = path_info(value)
            artifacts[("run_ref", info["path"])] = {"name": key, "role": "run_ref", **info}
    report_output_dir = source.get("report_output_dir")
    if isinstance(report_output_dir, str) and report_output_dir:
        info = path_info(report_output_dir, treat_as_dir=True)
        artifacts[("run_ref", info["path"])] = {"name": "report_output_dir", "role": "run_ref", **info}
    return sorted(artifacts.values(), key=lambda item: (item["role"], item["path"]))


def artifact_refs(refs: Any, *, role: str) -> list[dict[str, Any]]:
    if not isinstance(refs, dict):
        return []
    rows = []
    for name, value in refs.items():
        if not value:
            continue
        rows.append({"name": str(name), "role": role, **path_info(value)})
    return sorted(rows, key=lambda item: item["name"])


def checkpoint_artifacts(checkpoint: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not checkpoint:
        return []
    return list(checkpoint.get("output_artifacts", []))


def status_summary(statuses: Any) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    total = 0
    for value in statuses:
        if not value:
            continue
        counts[str(value)] += 1
        total += 1
    return {
        "total": total,
        "by_status": dict(sorted(counts.items())),
        "active": sum(counts.get(state, 0) for state in ("queued", "waiting", "running")),
        "terminal": sum(counts.get(state, 0) for state in TERMINAL_STATES),
        "blocked": counts.get("blocked", 0),
        "failed": counts.get("failed", 0) + counts.get("cancelled", 0),
        "succeeded": counts.get("succeeded", 0),
    }


def path_info(value: object, *, treat_as_dir: bool = False) -> dict[str, Any]:
    path = Path(str(value)).expanduser().resolve()
    exists = path.exists()
    info: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
        "is_dir": path.is_dir() if exists else bool(treat_as_dir),
    }
    if exists:
        info["size_bytes"] = path.stat().st_size if path.is_file() else None
    return info


def collect_callbacks(result: dict[str, Any]) -> list[dict[str, Any]]:
    callbacks = []
    publish = result.get("publish")
    if isinstance(publish, dict):
        callbacks.append({"type": "publish", "payload": publish})
    return callbacks


def task_logs(project_root: Path, task_id: str) -> list[dict[str, Any]]:
    from modnews.repository.task_logs import TaskLogRepository

    return TaskLogRepository(project_root).list(task_id, limit=200)


def build_domain_view(task: TaskEvent, result: dict[str, Any], checkpoints: list[dict[str, Any]]) -> dict[str, Any]:
    if task.type == "web_source.run":
        return {
            "kind": "web_source",
            "source_id": task.payload.get("source_id"),
            "job": result.get("job"),
            "repair_task_id": result.get("repair_task_id"),
        }
    if task.type == "extractor.repair.codex":
        repair_task = result.get("repair_task") if isinstance(result.get("repair_task"), dict) else {}
        return {
            "kind": "repair_codex",
            "source_id": repair_task.get("source_id") or task.payload.get("source_id"),
            "repair_task_id": task.payload.get("repair_task_id"),
            "repair_task": repair_task,
            "codex_log_path": result.get("codex_log_path"),
        }
    if task.type.startswith("classify."):
        return {
            "kind": "classify",
            "step_id": task.step_id,
            "run_id": task.pipeline_run_id,
            "checkpoint_path": checkpoints[-1].get("path") if checkpoints else result.get("checkpoint_path"),
            "batch_result": result.get("batch_result"),
        }
    if task.type == "report.generate":
        return {
            "kind": "report",
            "run_id": task.pipeline_run_id,
            "checkpoint_path": result.get("checkpoint_path"),
            "report_output_dir": result.get("report_output_dir"),
            "stats": result.get("stats"),
        }
    if task.type == "pipeline.combine_ingest":
        return {
            "kind": "pipeline_combine_ingest",
            "run_id": task.pipeline_run_id,
            "combined_ingest_path": result.get("combined_ingest_path"),
            "checkpoint_path": result.get("checkpoint_path"),
        }
    if task.type.startswith("ingest.") or task.type == "web_source.run":
        return {
            "kind": "ingest",
            "step_id": task.step_id,
            "run_id": task.pipeline_run_id,
            "checkpoint_path": result.get("checkpoint_path"),
        }
    return {
        "kind": "task",
        "type": task.type,
        "run_id": task.pipeline_run_id,
        "step_id": task.step_id,
    }
