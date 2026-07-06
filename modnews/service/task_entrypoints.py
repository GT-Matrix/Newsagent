from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews.service.pipeline.run_state import initialize_run_state, sync_run_state


def run_planned_tasks(
    *,
    project_root: Path,
    queue: Any,
    queue_show: Any,
    run_id: str,
    tasks: list[TaskEvent],
    create_payload: dict[str, Any],
) -> dict[str, Any]:
    runs = RunRepository(project_root)
    try:
        runs.get(run_id)
    except KeyError:
        runs.create(run_id, create_payload)
    for task in tasks:
        queue.register(task)
    initialize_run_state(project_root, run_id, _registered_tasks(queue, tasks))
    queue.drain_ready()
    sync_run_state(project_root, queue, run_id)
    task_payloads = [queue_show(task.id) for task in tasks]
    return {
        "ok": bool(task_payloads) and all(task.get("state") == "succeeded" for task in task_payloads),
        "run_id": run_id,
        "tasks": task_payloads,
        "run": runs.get(run_id),
    }


def _registered_tasks(queue: Any, tasks: list[TaskEvent]) -> list[TaskEvent]:
    return [queue.get(task.id) for task in tasks]
