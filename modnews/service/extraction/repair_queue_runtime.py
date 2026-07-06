from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue

from .repair_queue import build_repair_task_event


def has_repair_queue_task(queue: EventQueue, repair_task_id: str) -> bool:
    return find_repair_queue_task(queue, repair_task_id) is not None


def find_repair_queue_task(queue: EventQueue, repair_task_id: str):
    return next(
        (
            task
            for task in queue.list()
            if task.type == "extractor.repair.codex"
            and task.payload.get("repair_task_id") == repair_task_id
            and task.state not in {"cancelled", "failed"}
        ),
        None,
    )


def ensure_repair_queue_task(
    queue: EventQueue,
    *,
    project_root: Path,
    repair_task_id: str,
    source_id: str,
    run_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    existing = find_repair_queue_task(queue, repair_task_id)
    if existing is not None:
        return {
            "action": "reuse_repair_queue_task",
            "repair_task_id": repair_task_id,
            "source_id": source_id,
            "queue_task_id": existing.id,
            "queue_task_state": existing.state,
            "created": False,
        }
    queue_task = build_repair_task_event(
        project_root=project_root,
        repair_task_id=repair_task_id,
        source_id=source_id,
        run_id=run_id,
        task_id=task_id,
    )
    queue.submit(queue_task)
    current = queue.get(queue_task.id)
    return {
        "action": "submit_repair_queue_task",
        "repair_task_id": repair_task_id,
        "source_id": source_id,
        "queue_task_id": current.id,
        "queue_task_state": current.state,
        "created": True,
    }


def submit_repair_queue_task_detail(
    queue: EventQueue,
    *,
    queue_show,
    project_root: Path,
    repair_task_id: str,
    source_id: str,
    run_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    decision = ensure_repair_queue_task(
        queue,
        project_root=project_root,
        repair_task_id=repair_task_id,
        source_id=source_id,
        run_id=run_id,
        task_id=task_id,
    )
    task_detail = queue_show(str(decision["queue_task_id"]))
    return {
        **decision,
        "task": task_detail,
    }


def safely_skip_blocked_task(queue: EventQueue, task_id: str, *, reason: str) -> dict[str, Any]:
    current = queue.get(task_id)
    if current.state == "blocked":
        queue.skip(task_id, reason=reason)
        return {
            "action": "skip_blocked_task",
            "task_id": task_id,
            "reason": reason,
            "state": queue.get(task_id).state,
        }
    return {
        "action": "leave_task_state",
        "task_id": task_id,
        "reason": reason,
        "state": current.state,
    }


def handle_blocked_web_source_event(queue: EventQueue, event: dict[str, object]) -> dict[str, object] | None:
    task = event.get("task")
    result = event.get("result")
    if not isinstance(task, dict) or not isinstance(result, dict):
        return None
    if task.get("type") != "web_source.run":
        return None

    queue_actions: list[dict[str, Any]] = []
    task_id = str(task.get("id") or "")
    source_id = str(
        result.get("job", {}).get("source_id")
        if isinstance(result.get("job"), dict)
        else task.get("payload", {}).get("source_id") if isinstance(task.get("payload"), dict) else ""
    )
    repair_task_id = result.get("repair_task_id")
    payload = task.get("payload", {}) if isinstance(task.get("payload"), dict) else {}
    project_root = Path(str(payload.get("project_root") or Path.cwd())).resolve()
    run_id = str(task.get("pipeline_run_id") or "") or None

    if repair_task_id and source_id:
        queue_actions.append(
            ensure_repair_queue_task(
                queue,
                project_root=project_root,
                repair_task_id=str(repair_task_id),
                source_id=source_id,
                run_id=run_id,
            )
        )
    if task_id:
        queue_actions.append(
            safely_skip_blocked_task(
                queue,
                task_id,
                reason=str(result.get("blocked_reason") or "blocked web source safely skipped"),
            )
        )
    if not queue_actions:
        return None
    return {"repair_queue_actions": queue_actions}
