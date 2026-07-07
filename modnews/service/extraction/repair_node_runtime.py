from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue, current_queue
from modnews.core.progress import emit
from modnews.core.task import TaskBlocked, TaskEvent
from modnews.service.extraction.registry import registry_from_project
from modnews.service.extraction.repair_manager import RepairManager
from modnews.service.extraction.repair_task_result import build_repair_task_result

PREPARE_STAGE = "prepare"
EXEC_STAGE = "exec"
COMPLETED_STAGE = "completed"

REPAIR_EXEC_TASK_TYPE = "extractor.repair.codex.exec"


def run_codex_repair_node(task: TaskEvent) -> dict[str, object]:
    queue = _require_queue(current_queue())
    stage = _node_stage(task)
    if stage == EXEC_STAGE:
        return _complete_exec_stage(task, queue)
    return _start_repair_node(task, queue)


def run_codex_repair_exec_task(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    repair_task_id = str(task.payload["repair_task_id"])
    manager = RepairManager(project_root, registry_from_project(project_root))
    repair_task = manager.run_task_once(repair_task_id)
    return {"repair_task": repair_task.to_dict()}


def handle_repair_child_task_callback(event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]]:
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
    if parent.type != "extractor.repair.codex":
        return []
    summary = queue.group_summary(str(parent.payload.get("repair_exec_group_id") or ""))
    if summary["active"] > 0:
        return []
    queue.retry(parent.id)
    queue.drain_ready()
    return [{"action": "retry_parent_task", "task_id": parent.id, "stage": EXEC_STAGE}]


def _start_repair_node(task: TaskEvent, queue: EventQueue) -> dict[str, object]:
    submission = _register_exec_child(task, queue)
    queue.patch_payload(
        task.id,
        {
            "node_stage": EXEC_STAGE,
            "repair_exec_group_id": submission["group_id"],
            "repair_exec_task_ids": submission["task_ids"],
        },
    )
    raise TaskBlocked(
        "waiting for codex repair exec task",
        details={
            "kind": "child_task_group_active",
            "node_stage": EXEC_STAGE,
            "task_group_id": submission["group_id"],
        },
    )


def _complete_exec_stage(task: TaskEvent, queue: EventQueue) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    repair_task_id = str(task.payload["repair_task_id"])
    child_task_id = _single_task_id(task.payload.get("repair_exec_task_ids"))
    child = queue.get(child_task_id)
    if child.state != "succeeded":
        reason = _task_error(queue, child)
        raise TaskBlocked(
            reason or "repair exec task blocked",
            details={
                "safe_skip": True,
                "child_task_id": child.id,
                "child_state": child.state,
                "repair_task_id": repair_task_id,
            },
        )
    manager = RepairManager(project_root, registry_from_project(project_root))
    repair_task = manager.finalize_task(repair_task_id)
    repair_task_payload = manager.get_task(repair_task_id)
    log_summary = manager.store.codex_log_summary(repair_task_id)
    emit(
        "codex_repair_log",
        repair_task_id=repair_task.id,
        source_id=repair_task.source_id,
        status=repair_task.status,
        **log_summary,
    )
    result = build_repair_task_result(repair_task_payload, log_summary)
    result["node_stage"] = COMPLETED_STAGE
    return result


def _register_exec_child(task: TaskEvent, queue: EventQueue) -> dict[str, object]:
    group_id = f"{task.id}:exec"
    child = TaskEvent(
        id=f"{task.id}:exec:1",
        type=REPAIR_EXEC_TASK_TYPE,
        pipeline_run_id=task.pipeline_run_id,
        step_id=f"{task.step_id}/exec" if task.step_id else "extractor/repair/exec",
        parent_task_id=task.id,
        task_group_id=group_id,
        payload=dict(task.payload),
        concurrency_key=task.concurrency_key,
        max_concurrency=task.max_concurrency,
        priority=task.priority,
    )
    queue.register(child)
    return {"group_id": group_id, "task_ids": [child.id]}


def _single_task_id(values: object) -> str:
    items = [str(item) for item in values or []]
    if not items:
        raise RuntimeError("expected repair child task id")
    return items[0]


def _task_error(queue: EventQueue, task: TaskEvent) -> str | None:
    result = queue.result(task.id)
    for key in ("blocked_reason", "error"):
        value = result.get(key)
        if value:
            return str(value)
    if task.status_reason:
        return str(task.status_reason)
    return None


def _node_stage(task: TaskEvent) -> str:
    return str(task.payload.get("node_stage") or task.payload.get("stage") or PREPARE_STAGE)


def _require_queue(value: object) -> EventQueue:
    if isinstance(value, EventQueue):
        return value
    raise RuntimeError("repair node requires active event queue")
