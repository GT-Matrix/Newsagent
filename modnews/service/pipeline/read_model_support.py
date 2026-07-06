from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import SUCCESS_STATES, TERMINAL_STATES, TaskEvent
from modnews.service.pipeline.step import PipelineStepDescriptor


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


def build_pipeline_step_views(
    descriptors: list[PipelineStepDescriptor],
    concrete_steps: list[dict[str, Any]],
    *,
    status_overrides: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    concrete_by_step_id = {
        str(step.get("step_id") or ""): step
        for step in concrete_steps
        if isinstance(step, dict) and step.get("step_id")
    }
    rows: list[dict[str, Any]] = []
    for descriptor in descriptors:
        matched_steps = [
            step
            for step_id, step in concrete_by_step_id.items()
            if _matches_pipeline_descriptor(descriptor, step_id)
        ]
        concrete_step_ids = sorted(str(step.get("step_id") or "") for step in matched_steps if step.get("step_id"))
        latest_checkpoint = _latest_pipeline_checkpoint(matched_steps)
        row = {
            "step_id": descriptor.step_id,
            "title": descriptor.title,
            "group": descriptor.group,
            "kind": descriptor.kind,
            "description": descriptor.description,
            "depends_on": list(descriptor.depends_on),
            "callback_handlers": list(descriptor.callback_handlers),
            "followups": [
                {
                    "trigger": followup.trigger,
                    "builder_id": followup.builder_id,
                    "task_type": followup.task_type,
                    "step_prefix": followup.step_prefix,
                }
                for followup in descriptor.followups
            ],
            "concrete_step_ids": concrete_step_ids,
            "status": _aggregate_pipeline_step_status(matched_steps),
            "task_ids": _merge_step_ids(matched_steps, "task_ids"),
            "queued_task_ids": _merge_step_ids(matched_steps, "queued_task_ids"),
            "completed_task_ids": _merge_step_ids(matched_steps, "completed_task_ids"),
            "blocked_task_ids": _merge_step_ids(matched_steps, "blocked_task_ids"),
            "skipped_task_ids": _merge_step_ids(matched_steps, "skipped_task_ids"),
            "failed_task_ids": _merge_step_ids(matched_steps, "failed_task_ids"),
            "checkpoint_count": sum(int(step.get("checkpoint_count") or 0) for step in matched_steps),
            "latest_checkpoint": latest_checkpoint,
            "artifacts": checkpoint_artifacts(latest_checkpoint),
            "stats": latest_checkpoint.get("stats", {}) if latest_checkpoint else {},
            "callback_events": _merge_callback_events(matched_steps),
        }
        if row["status"] == "idle":
            override = (status_overrides or {}).get(descriptor.step_id)
            if override:
                row["status"] = override
        rows.append(row)
    return rows


def pipeline_status_overrides(run_payload: Any) -> dict[str, str]:
    if not isinstance(run_payload, dict):
        return {}
    overrides: dict[str, str] = {}
    if bool(run_payload.get("disable_classification")):
        overrides["pipeline_classify"] = "skipped"
        overrides["pipeline_report"] = "skipped"
        return overrides
    if bool(run_payload.get("disable_report")):
        overrides["pipeline_report"] = "skipped"
    return overrides


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
    checkpoints = []
    domain_view = build_domain_view(task, result, checkpoints)
    related_artifacts = collect_artifacts(result, checkpoints)
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
    payload["title"] = task_title(task)
    payload["summary"] = task_display_summary(
        task,
        result,
        blocked_reason=blocked_reason,
        waiting_reason=waiting_reason,
        checkpoint_path=None,
    )
    payload["log_kind"] = task_log_kind(task)
    payload["detail_kind"] = task_detail_kind(task)
    payload["retry_state"] = build_retry_state(task, result)
    payload["blocked_state"] = build_blocked_state(task, blocked_reason, blocked_details)
    payload["related_run_id"] = task.pipeline_run_id
    payload["related_step_id"] = task.step_id
    payload["related_source_id"] = related_source_id(task, result)
    payload["related_checkpoint_path"] = related_checkpoint_path(result, checkpoints)
    payload["related_artifacts"] = related_artifacts
    payload["domain_view"] = domain_view
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


def task_title(task: TaskEvent) -> str:
    if task.type == "pipeline.combine_ingest":
        return "Combine ingest outputs"
    if task.type == "report.generate":
        return "Generate report"
    if task.type == "web_source.run":
        source_id = str(task.payload.get("source_id") or "")
        return f"Run web source {source_id}" if source_id else "Run web source"
    if task.type == "extractor.repair.codex":
        source_id = str(task.payload.get("source_id") or "")
        return f"Run extractor repair {source_id}" if source_id else "Run extractor repair"
    if task.type == "classify.clustered_event_extraction":
        return "Classify clustered event extraction"
    if task.type == "classify.clustered_event_merge":
        return "Classify clustered event merge"
    if task.type == "classify.embedding":
        return _batch_title("Classify embedding batch", task)
    if task.type == "classify.batch_relevance":
        return _batch_title("Classify relevance batch", task)
    if task.type.endswith(".batch"):
        return _batch_title(task.type, task)
    if task.type.startswith("ingest."):
        return f"Run ingest task {task.type.removeprefix('ingest.')}"
    if task.type.startswith("classify."):
        return f"Run classify task {task.type.removeprefix('classify.')}"
    return task.type


def task_log_kind(task: TaskEvent) -> str:
    if task.type == "extractor.repair.codex":
        return "codex"
    if task.type == "web_source.run":
        return "web_job"
    if task.type.startswith("classify."):
        return "classify"
    if task.type == "report.generate":
        return "report"
    return "task"


def task_detail_kind(task: TaskEvent) -> str:
    if task.type == "extractor.repair.codex":
        return "repair_task"
    if task.type == "web_source.run":
        return "web_source_task"
    if task.type.startswith("classify."):
        return "classify_task"
    if task.type == "report.generate":
        return "report_task"
    if task.type.startswith("ingest.") or task.type == "pipeline.combine_ingest":
        return "ingest_task"
    return "task"


def build_retry_state(task: TaskEvent, result: dict[str, Any]) -> dict[str, Any]:
    attempts_used = max(int(task.attempt or 0), 0)
    max_attempts = max(int(task.max_attempts or 1), 1)
    next_attempt_at = result.get("next_attempt_at") or task.next_attempt_at
    retry_scheduled = bool(result.get("retry_scheduled"))
    if retry_scheduled or task.state == "waiting":
        status = "scheduled"
    elif task.state == "running" and max_attempts > 1:
        status = "running"
    elif attempts_used > 0 or task.state in {"failed", "cancelled", "blocked"}:
        status = "attempted"
    else:
        status = "idle"
    return {
        "status": status,
        "attempt": attempts_used,
        "max_attempts": max_attempts,
        "remaining_attempts": max(max_attempts - attempts_used, 0),
        "retry_backoff_seconds": int(task.retry_backoff_seconds or 0),
        "retry_delay_seconds": result.get("retry_delay_seconds"),
        "next_attempt_at": next_attempt_at,
        "scheduled": retry_scheduled,
    }


def build_blocked_state(
    task: TaskEvent,
    blocked_reason: str | None,
    blocked_details: dict[str, Any] | None,
) -> dict[str, Any]:
    kind = None
    if isinstance(blocked_details, dict):
        kind = blocked_details.get("kind")
    safe_to_skip = bool(kind in {"dependency", "business"})
    return {
        "blocked": task.state == "blocked" or bool(blocked_reason),
        "reason": blocked_reason,
        "details": blocked_details,
        "kind": kind,
        "safe_to_skip": safe_to_skip,
    }


def related_source_id(task: TaskEvent, result: dict[str, Any]) -> str | None:
    source_id = task.payload.get("source_id")
    if isinstance(source_id, str) and source_id:
        return source_id
    job = result.get("job")
    if isinstance(job, dict):
        job_source_id = job.get("source_id")
        if isinstance(job_source_id, str) and job_source_id:
            return job_source_id
    repair_task = result.get("repair_task")
    if isinstance(repair_task, dict):
        repair_source_id = repair_task.get("source_id")
        if isinstance(repair_source_id, str) and repair_source_id:
            return repair_source_id
    return None


def related_checkpoint_path(result: dict[str, Any], checkpoints: list[dict[str, Any]]) -> str | None:
    if checkpoints:
        latest = checkpoints[-1].get("path")
        if isinstance(latest, str) and latest:
            return latest
    checkpoint_path = result.get("checkpoint_path")
    if isinstance(checkpoint_path, str) and checkpoint_path:
        return checkpoint_path
    return None


def task_display_summary(
    task: TaskEvent,
    result: dict[str, Any],
    *,
    blocked_reason: str | None,
    waiting_reason: str | None,
    checkpoint_path: str | None,
) -> str:
    if task.state == "blocked" and blocked_reason:
        return blocked_reason
    if task.state == "waiting" and waiting_reason:
        return waiting_reason
    if task.state == "failed" and result.get("error"):
        return str(result.get("error"))
    if task.state == "cancelled" and result.get("cancel_reason"):
        return str(result.get("cancel_reason"))
    if task.state == "skipped" and result.get("skip_reason"):
        return str(result.get("skip_reason"))
    if task.type == "report.generate" and isinstance(result.get("stats"), dict):
        stats = result["stats"]
        selected = stats.get("selected_count")
        if selected is not None:
            return f"selected_count={selected}"
    if task.type == "web_source.run":
        job = result.get("job")
        if isinstance(job, dict):
            job_id = job.get("id")
            job_state = job.get("state")
            if job_id or job_state:
                return f"job={job_id or 'unknown'} state={job_state or 'unknown'}"
    if checkpoint_path:
        return checkpoint_path
    if task.state == "succeeded":
        return "completed"
    return task.state


def build_attempt_history(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    interesting_types = {
        "task.registered",
        "task.started",
        "task.waiting",
        "task.retry_scheduled",
        "task.retry_requested",
        "task.completed",
        "task.failed",
        "task.blocked",
        "task.cancelled",
        "task.skipped",
        "task.unblocked",
    }
    for entry in logs:
        if not isinstance(entry, dict):
            continue
        event_type = str(entry.get("type") or "")
        if event_type not in interesting_types:
            continue
        rows.append(
            {
                "ts": entry.get("ts"),
                "type": event_type,
                "state": entry.get("state"),
                "attempt": entry.get("attempt"),
                "error": entry.get("error"),
                "reason": entry.get("reason"),
            }
        )
    return rows


def _batch_title(base: str, task: TaskEvent) -> str:
    batch = task.payload.get("batch")
    if isinstance(batch, dict):
        batch_index = batch.get("batch_index")
        batch_count = batch.get("batch_count")
        if isinstance(batch_index, int) and isinstance(batch_count, int):
            return f"{base} [{batch_index}/{batch_count}]"
    return base


def _matches_pipeline_descriptor(descriptor: PipelineStepDescriptor, step_id: str) -> bool:
    if step_id == descriptor.step_id:
        return True
    if step_id in descriptor.concrete_step_ids:
        return True
    return any(step_id.startswith(prefix) for prefix in descriptor.concrete_step_prefixes)


def _aggregate_pipeline_step_status(steps: list[dict[str, Any]]) -> str:
    statuses = [str(step.get("status") or "") for step in steps if step.get("status")]
    if not statuses:
        return "idle"
    if "failed" in statuses:
        return "failed"
    if "blocked" in statuses:
        return "blocked"
    if "running" in statuses:
        return "running"
    if "queued" in statuses:
        return "queued"
    if "partial" in statuses:
        return "partial"
    if all(status == "succeeded" for status in statuses):
        return "succeeded"
    return statuses[-1]


def _merge_step_ids(steps: list[dict[str, Any]], key: str) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for step in steps:
        for value in step.get(key, []):
            if not isinstance(value, str) or value in seen:
                continue
            seen.add(value)
            merged.append(value)
    return merged


def _latest_pipeline_checkpoint(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    latest_key = ""
    for step in steps:
        checkpoint = step.get("latest_checkpoint")
        if not isinstance(checkpoint, dict):
            continue
        key = str(checkpoint.get("finished_at") or checkpoint.get("started_at") or checkpoint.get("path") or "")
        if key >= latest_key:
            latest = checkpoint
            latest_key = key
    return latest


def _merge_callback_events(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for step in steps:
        for event in step.get("callback_events", []):
            if isinstance(event, dict) and event.get("handler"):
                rows.append(event)
    return rows[-50:]


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
