from __future__ import annotations

from datetime import datetime
from pathlib import Path

from modnews.core.task import TaskEvent
from .task_registry import (
    REGISTERED_CLASSIFY_TASKS,
    build_registered_classify_task,
    get_registered_classify_task,
)


def resolve_clustered_classify_run_id(run_id: str | None) -> str:
    return run_id or f"classify-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def build_clustered_event_extraction_task(
    *,
    project_root: Path,
    run_id: str,
    input_path: str | None,
    config: str | None = None,
    depends_on: list[str] | None = None,
) -> TaskEvent:
    return build_registered_classify_task(
        get_registered_classify_task("classify.clustered_event_extraction"),
        project_root=project_root,
        run_id=run_id,
        input_path=input_path,
        config=config,
        depends_on=depends_on,
    )


def build_clustered_event_merge_task(
    *,
    project_root: Path,
    run_id: str,
    input_path: str | None,
    config: str | None = None,
    depends_on: list[str] | None = None,
) -> TaskEvent:
    return build_registered_classify_task(
        get_registered_classify_task("classify.clustered_event_merge"),
        project_root=project_root,
        run_id=run_id,
        input_path=input_path,
        config=config,
        depends_on=depends_on,
    )


def plan_clustered_classify_tasks(
    *,
    project_root: Path,
    run_id: str | None,
    input_path: str | None,
    config: str | None = None,
) -> list[TaskEvent]:
    task_run_id = resolve_clustered_classify_run_id(run_id)
    tasks: list[TaskEvent] = []
    depends_on: list[str] = []
    for spec in REGISTERED_CLASSIFY_TASKS:
        task = build_registered_classify_task(
            spec,
            project_root=project_root,
            run_id=task_run_id,
            input_path=input_path,
            config=config,
            depends_on=depends_on,
        )
        tasks.append(task)
        depends_on = [task.id]
    return tasks
