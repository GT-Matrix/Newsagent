from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews.service.pipeline.runtime_store import overlay_run_record
from modnews.service.pipeline.run_state import initialize_run_state, sync_run_state
from modnews.service.pipeline.step import PipelineStepDescriptor


def run_planned_tasks(
    *,
    project_root: Path,
    queue: Any,
    queue_show: Any,
    run_id: str,
    tasks: list[TaskEvent],
    create_payload: dict[str, Any],
    task_result_scope: str = "initial",
    pipeline_descriptors: list[PipelineStepDescriptor] | None = None,
) -> dict[str, Any]:
    runs = RunRepository(project_root)
    try:
        runs.get(run_id)
    except KeyError:
        runs.create(run_id, create_payload)
    for task in tasks:
        queue.register(task)
    initialize_run_state(project_root, run_id, _registered_tasks(queue, tasks), pipeline_descriptors=pipeline_descriptors)
    queue.drain_ready()
    sync_run_state(project_root, queue, run_id, pipeline_descriptors=pipeline_descriptors)
    task_payloads = _task_payloads(queue, queue_show, run_id, tasks, scope=task_result_scope)
    return {
        "ok": bool(task_payloads) and all(task.get("state") == "succeeded" for task in task_payloads),
        "run_id": run_id,
        "tasks": task_payloads,
        "run": overlay_run_record(project_root, runs.get(run_id)),
    }


def _registered_tasks(queue: Any, tasks: list[TaskEvent]) -> list[TaskEvent]:
    return [queue.get(task.id) for task in tasks]


def _task_payloads(
    queue: Any,
    queue_show: Any,
    run_id: str,
    tasks: list[TaskEvent],
    *,
    scope: str,
) -> list[dict[str, Any]]:
    if scope == "run":
        run_task_ids = [
            task.id
            for task in queue.list()
            if task.pipeline_run_id == run_id
        ]
        return [queue_show(task_id) for task_id in run_task_ids]
    return [queue_show(task.id) for task in tasks]
