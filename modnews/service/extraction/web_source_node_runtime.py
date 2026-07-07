from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue, current_queue
from modnews.core.task import TaskBlocked, TaskEvent
from modnews.repository.runs import RunRepository
from modnews.repository.source_config import source_config_store
from modnews.service.extraction.orchestrator import WebExtractionOrchestrator
from modnews.service.extraction.repair_queue import build_repair_task_event
from modnews.service.extraction.web_contract import WebJob, WebSource
from modnews.service.pipeline.checkpoint import CheckpointManager

PREPARE_STAGE = "prepare"
SCRAPE_STAGE = "scrape"
REPAIR_STAGE = "repair"
COMPLETED_STAGE = "completed"

SCRAPE_TASK_TYPE = "web_source.scrape"


def run_web_source_node(task: TaskEvent) -> dict[str, object]:
    queue = _require_queue(current_queue())
    stage = _node_stage(task)
    if stage == SCRAPE_STAGE:
        return _complete_scrape_stage(task, queue)
    if stage == REPAIR_STAGE:
        return _complete_repair_stage(task, queue)
    return _start_web_source_node(task, queue)


def run_web_source_scrape_task(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    source_id = str(task.payload["source_id"])
    config = source_config_store(project_root).load()
    raw = config.get("sources", {}).get("site_lists", {}).get(source_id)
    if not isinstance(raw, dict):
        raise ValueError(f"source not found: {source_id}")
    source = WebSource.from_config(source_id, raw)
    if not source.enabled:
        raise ValueError(f"source is disabled: {source_id}")
    limit = int(task.payload.get("limit") or config.get("steps", {}).get("site_lists", {}).get("limit_per_site", 10))
    scrape_date = str(task.payload.get("scrape_date") or datetime.now().astimezone().isoformat(timespec="seconds"))
    job = WebExtractionOrchestrator(project_root).run_source(source, scrape_date=scrape_date, limit=limit)
    return {
        "job": job.to_dict(),
        "source_id": source_id,
        "scrape_date": scrape_date,
    }


def handle_web_source_child_task_callback(event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]]:
    if queue is None:
        return []
    task = event.get("task")
    if not isinstance(task, dict):
        return []
    parent_task_id = task.get("parent_task_id")
    if not parent_task_id:
        return []
    try:
        parent = queue.get(str(parent_task_id))
    except KeyError:
        return []
    if parent.type != "web_source.run":
        return []
    stage = str(queue.result(parent.id).get("node_stage") or _node_stage(parent))
    if stage == SCRAPE_STAGE:
        return _handle_child_group_completion(parent, queue, "scrape_group_id", SCRAPE_STAGE)
    if stage == REPAIR_STAGE:
        return _handle_child_group_completion(parent, queue, "repair_group_id", REPAIR_STAGE)
    return []


def _start_web_source_node(task: TaskEvent, queue: EventQueue) -> dict[str, object]:
    submission = _register_scrape_child(task, queue)
    queue.patch_payload(
        task.id,
        {
            "node_stage": SCRAPE_STAGE,
            "scrape_group_id": submission["group_id"],
            "scrape_task_ids": submission["task_ids"],
            "scrape_round": 1,
        },
    )
    raise TaskBlocked(
        "waiting for web source scrape task",
        details={
            "kind": "child_task_group_active",
            "node_stage": SCRAPE_STAGE,
            "task_group_id": submission["group_id"],
        },
    )


def _complete_scrape_stage(task: TaskEvent, queue: EventQueue) -> dict[str, object]:
    payload = task.payload
    scrape_task_id = _single_task_id(payload.get("scrape_task_ids"))
    child = queue.get(scrape_task_id)
    if child.state != "succeeded":
        reason = _task_error(queue, child)
        raise TaskBlocked(
            reason or "web source scrape task blocked",
            details={
                "safe_skip": True,
                "child_task_id": child.id,
                "child_state": child.state,
            },
        )
    child_result = queue.result(scrape_task_id)
    job_payload = child_result.get("job")
    if not isinstance(job_payload, dict):
        raise RuntimeError("web source scrape result missing job payload")
    job = WebJob(**job_payload)
    if job.state == "succeeded":
        result = _persist_web_source_checkpoint(task, job)
        result["node_stage"] = COMPLETED_STAGE
        return result
    if job.state in {"repair_queued", "repairing"} and job.repair_task_id:
        submission = _register_repair_child(task, queue, repair_task_id=job.repair_task_id, source_id=job.source_id)
        queue.patch_payload(
            task.id,
            {
                "node_stage": REPAIR_STAGE,
                "repair_group_id": submission["group_id"],
                "repair_task_ids": submission["task_ids"],
                "repair_task_id": job.repair_task_id,
            },
        )
        raise TaskBlocked(
            f"waiting for extractor repair task {job.repair_task_id}",
            details={
                "kind": "child_task_group_active",
                "node_stage": REPAIR_STAGE,
                "task_group_id": submission["group_id"],
                "repair_task_id": job.repair_task_id,
                "job": job.to_dict(),
            },
        )
    if job.state == "skipped_unrepairable":
        raise TaskBlocked(
            job.error or f"web source {job.source_id} is blocked",
            details={
                "job": job.to_dict(),
                "error_type": job.error_type,
                "safe_skip": True,
            },
        )
    raise RuntimeError(job.error or f"web source {job.source_id} ended as {job.state}")


def _complete_repair_stage(task: TaskEvent, queue: EventQueue) -> dict[str, object]:
    payload = task.payload
    repair_task_id = _single_task_id(payload.get("repair_task_ids"))
    child = queue.get(repair_task_id)
    if child.state != "succeeded":
        reason = _task_error(queue, child)
        raise TaskBlocked(
            reason or "extractor repair task blocked",
            details={
                "safe_skip": True,
                "child_task_id": child.id,
                "child_state": child.state,
                "repair_task_id": payload.get("repair_task_id"),
            },
        )
    next_round = int(payload.get("scrape_round") or 1) + 1
    submission = _register_scrape_child(task, queue, round_index=next_round)
    queue.patch_payload(
        task.id,
        {
            "node_stage": SCRAPE_STAGE,
            "scrape_group_id": submission["group_id"],
            "scrape_task_ids": submission["task_ids"],
            "scrape_round": next_round,
        },
    )
    raise TaskBlocked(
        "waiting for repaired web source scrape task",
        details={
            "kind": "child_task_group_active",
            "node_stage": SCRAPE_STAGE,
            "task_group_id": submission["group_id"],
            "scrape_round": next_round,
        },
    )


def _persist_web_source_checkpoint(task: TaskEvent, job: WebJob) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    run_id = task.pipeline_run_id or str(task.payload.get("run_id") or "manual")
    checkpoint = CheckpointManager(project_root)
    rows: list[dict[str, Any]] = []
    if job.output_path:
        try:
            payload = json.loads(Path(job.output_path).read_text(encoding="utf-8"))
            rows = payload if isinstance(payload, list) else []
        except Exception:
            rows = []
    artifact_path = checkpoint.write_artifact(run_id, f"ingest/site_lists/{job.source_id}", task.id, "items.json", rows)
    checkpoint_payload = {
        "run_id": run_id,
        "step_id": f"ingest/site_lists/{job.source_id}",
        "task_id": task.id,
        "status": "succeeded",
        "input_refs": {},
        "output_refs": {
            "items": str(artifact_path),
            **({"job_output": str(job.output_path)} if job.output_path else {}),
        },
        "stats": {"item_count": len(rows), "job_id": job.id},
        "error": None,
    }
    checkpoint_path = checkpoint.write(run_id, f"ingest/site_lists/{job.source_id}", task.id, checkpoint_payload)
    RunRepository(project_root).append_checkpoint(run_id, checkpoint_path, create_payload={"source": "web_source_task"})
    return {
        "job": job.to_dict(),
        "checkpoint_path": str(checkpoint_path),
        "artifact_path": str(artifact_path),
        "item_count": len(rows),
    }


def _register_scrape_child(task: TaskEvent, queue: EventQueue, *, round_index: int = 1) -> dict[str, object]:
    group_id = f"{task.id}:scrape:{round_index}"
    child = TaskEvent(
        id=f"{task.id}:scrape:{round_index}",
        type=SCRAPE_TASK_TYPE,
        pipeline_run_id=task.pipeline_run_id,
        step_id=f"{task.step_id}/scrape" if task.step_id else "web_source/scrape",
        parent_task_id=task.id,
        task_group_id=group_id,
        payload=dict(task.payload),
        concurrency_key=task.concurrency_key,
        max_concurrency=task.max_concurrency,
        priority=task.priority,
    )
    queue.register(child)
    return {"group_id": group_id, "task_ids": [child.id]}


def _register_repair_child(
    task: TaskEvent,
    queue: EventQueue,
    *,
    repair_task_id: str,
    source_id: str,
) -> dict[str, object]:
    group_id = f"{task.id}:repair"
    child = build_repair_task_event(
        project_root=Path(str(task.payload.get("project_root") or Path.cwd())).resolve(),
        repair_task_id=repair_task_id,
        source_id=source_id,
        run_id=task.pipeline_run_id,
        task_id=f"{task.id}:repair:{repair_task_id}",
    )
    child.parent_task_id = task.id
    child.task_group_id = group_id
    child.depends_on = []
    child.priority = task.priority
    queue.register(child)
    return {"group_id": group_id, "task_ids": [child.id]}


def _handle_child_group_completion(
    parent: TaskEvent,
    queue: EventQueue,
    group_key: str,
    stage: str,
) -> list[dict[str, Any]]:
    summary = queue.group_summary(str(parent.payload.get(group_key) or ""))
    if summary["active"] > 0:
        return []
    queue.retry(parent.id)
    queue.drain_ready()
    return [{"action": "retry_parent_task", "task_id": parent.id, "stage": stage}]


def _task_error(queue: EventQueue, task: TaskEvent) -> str | None:
    result = queue.result(task.id)
    for key in ("blocked_reason", "error"):
        value = result.get(key)
        if value:
            return str(value)
    if task.status_reason:
        return str(task.status_reason)
    return None


def _single_task_id(values: object) -> str:
    items = [str(item) for item in values or []]
    if not items:
        raise RuntimeError("expected child task id")
    return items[0]


def _node_stage(task: TaskEvent) -> str:
    return str(task.payload.get("node_stage") or task.payload.get("stage") or PREPARE_STAGE)


def _require_queue(value: object) -> EventQueue:
    if isinstance(value, EventQueue):
        return value
    raise RuntimeError("web source node requires active event queue")
