from __future__ import annotations

from datetime import datetime
from pathlib import Path

from modnews.core.task import TaskEvent


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
    return TaskEvent(
        id=f"classify-{run_id}-clustered-event-extraction",
        type="classify.clustered_event_extraction",
        pipeline_run_id=run_id,
        step_id="classify/clustered_event_extraction",
        payload={
            "project_root": str(project_root),
            "run_id": run_id,
            "config": config,
            "input_path": input_path,
        },
        depends_on=list(depends_on or []),
        concurrency_key="classify",
        max_concurrency=1,
    )


def build_clustered_event_merge_task(
    *,
    project_root: Path,
    run_id: str,
    input_path: str | None,
    config: str | None = None,
    depends_on: list[str] | None = None,
) -> TaskEvent:
    return TaskEvent(
        id=f"classify-{run_id}-clustered-event-merge",
        type="classify.clustered_event_merge",
        pipeline_run_id=run_id,
        step_id="classify/clustered_event_merge",
        payload={
            "project_root": str(project_root),
            "run_id": run_id,
            "config": config,
            "input_path": input_path,
        },
        depends_on=list(depends_on or []),
        concurrency_key="classify",
        max_concurrency=1,
    )


def plan_clustered_classify_tasks(
    *,
    project_root: Path,
    run_id: str | None,
    input_path: str | None,
    config: str | None = None,
) -> list[TaskEvent]:
    task_run_id = resolve_clustered_classify_run_id(run_id)
    extraction_task = build_clustered_event_extraction_task(
        project_root=project_root,
        run_id=task_run_id,
        input_path=input_path,
        config=config,
    )
    merge_task = build_clustered_event_merge_task(
        project_root=project_root,
        run_id=task_run_id,
        input_path=input_path,
        config=config,
        depends_on=[extraction_task.id],
    )
    return [extraction_task, merge_task]
