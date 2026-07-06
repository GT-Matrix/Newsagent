from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews.service.ingest.planner import plan_ingest_tasks
from modnews.service.pipeline.run_state import initialize_run_state, sync_run_state


def run_ingest_step_tasks(
    *,
    project_root: Path,
    queue: Any,
    queue_show: Any,
    step_id: str,
    run_id: str | None = None,
    config_path: object = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_run_id = run_id or f"ingest-{step_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    tasks = plan_ingest_tasks(
        project_root=project_root,
        step_id=step_id,
        run_id=task_run_id,
        config_path=config_path,
        options=options,
    )
    runs = RunRepository(project_root)
    try:
        runs.get(task_run_id)
    except KeyError:
        runs.create(task_run_id, {"source": "manual_ingest_entrypoint", "step_id": step_id, "options": options or {}})
    for task in tasks:
        queue.register(task)
    initialize_run_state(project_root, task_run_id, _registered_tasks(queue, tasks))
    queue.drain_ready()
    sync_run_state(project_root, queue, task_run_id)
    task_payloads = [queue_show(task.id) for task in tasks]
    return {
        "ok": bool(task_payloads) and all(task.get("state") == "succeeded" for task in task_payloads),
        "run_id": task_run_id,
        "tasks": task_payloads,
        "run": runs.get(task_run_id),
    }


def _registered_tasks(queue: Any, tasks: list[TaskEvent]) -> list[TaskEvent]:
    return [queue.get(task.id) for task in tasks]
