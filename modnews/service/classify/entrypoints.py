from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews.service.classify.planner import (
    build_clustered_event_extraction_task,
    resolve_clustered_classify_run_id,
)
from modnews.service.pipeline.run_state import initialize_run_state, sync_run_state


def run_classify_tasks(
    *,
    project_root: Path,
    queue: Any,
    queue_show: Any,
    run_id: str | None,
    input_path: str | None,
    config: str | None = None,
) -> dict[str, Any]:
    task_run_id = resolve_clustered_classify_run_id(run_id)
    extraction_task = build_clustered_event_extraction_task(
        project_root=project_root,
        run_id=str(task_run_id),
        input_path=input_path,
        config=config,
    )
    runs = RunRepository(project_root)
    try:
        runs.get(str(task_run_id))
    except KeyError:
        runs.create(str(task_run_id), {"source": "manual_classify_entrypoint", "input_path": input_path, "config": config})
    queue.register(extraction_task)
    initialize_run_state(project_root, str(task_run_id), [_registered_task(queue, extraction_task)])
    queue.drain_ready()
    sync_run_state(project_root, queue, str(task_run_id))
    task_payloads = _run_tasks(queue, queue_show, str(task_run_id))
    return {
        "ok": bool(task_payloads) and all(task.get("state") == "succeeded" for task in task_payloads),
        "run_id": str(task_run_id),
        "tasks": task_payloads,
        "run": runs.get(str(task_run_id)),
    }


def _registered_task(queue: Any, task: TaskEvent) -> TaskEvent:
    return queue.get(task.id)


def _run_tasks(queue: Any, queue_show: Any, run_id: str) -> list[dict[str, Any]]:
    return [
        queue_show(task.id)
        for task in queue.list()
        if task.pipeline_run_id == run_id
    ]
