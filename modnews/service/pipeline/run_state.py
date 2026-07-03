from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import SUCCESS_STATES, TERMINAL_STATES
from modnews.repository.runs import RunRepository


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
        for key in ("checkpoint_path", "combined_ingest_path", "stats"):
            if key in result:
                updates[key] = result[key]
        if "error" in result:
            updates["error"] = result["error"]
        if "blocked_reason" in result:
            updates["blocked_reason"] = result["blocked_reason"]
    run_tasks = [item for item in queue.list() if item.pipeline_run_id == run_id]
    if run_tasks:
        if any(item.state == "failed" for item in run_tasks):
            updates["state"] = "failed"
        elif any(item.state == "blocked" for item in run_tasks):
            updates["state"] = "blocked"
        elif all(item.state in TERMINAL_STATES for item in run_tasks):
            updates["state"] = "succeeded" if all(item.state == "succeeded" for item in run_tasks) else "partial"
        elif all(item.state in SUCCESS_STATES for item in run_tasks):
            updates["state"] = "succeeded" if all(item.state == "succeeded" for item in run_tasks) else "partial"
    try:
        RunRepository(Path(str(project_root))).update(str(run_id), **updates)
    except KeyError:
        return
