from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.task import TaskEvent
from modnews.service.classify.planner import (
    build_clustered_event_extraction_task,
    build_clustered_event_merge_task,
)
from modnews.service.ingest.planner import plan_ingest_tasks
from modnews.service.report.task_registry import (
    build_registered_report_task,
    get_registered_report_task,
)


def build_ingest_tasks(*, project_root: str, run_id: str, config_path: object, config: Any) -> list[TaskEvent]:
    ingest_tasks: list[TaskEvent] = []
    for step in config.ingest_steps:
        if not step.enabled:
            continue
        ingest_tasks.extend(
            plan_ingest_tasks(
                project_root=Path(project_root) if project_root else Path.cwd(),
                step_id=step.type,
                run_id=run_id,
                config_path=config_path,
                options=step.options,
            )
        )
    return ingest_tasks

def build_combine_ingest_task_for_run(*, run_id: str, project_root: str, ingest_task_ids: list[str]) -> list[TaskEvent]:
    if not ingest_task_ids:
        return []
    return [
        TaskEvent(
            id=f"pipeline-{run_id}-combine-ingest",
            type="pipeline.combine_ingest",
            pipeline_run_id=run_id,
            step_id="pipeline/combine_ingest",
            payload={"project_root": project_root, "run_id": run_id},
            depends_on=ingest_task_ids,
            concurrency_key=f"pipeline:{run_id}",
            max_concurrency=1,
        )
    ]

def build_classify_extraction_task(
    *,
    run_id: str,
    project_root: str,
    config_path: object,
    depends_on: list[str],
) -> TaskEvent:
    return build_clustered_event_extraction_task(
        project_root=Path(project_root) if project_root else Path.cwd(),
        run_id=run_id,
        input_path="__combined_ingest__",
        config=str(config_path) if config_path is not None else None,
        depends_on=depends_on,
    )


def build_classify_merge_task(
    *,
    run_id: str,
    project_root: str,
    config_path: object,
    depends_on: list[str],
) -> TaskEvent:
    return build_clustered_event_merge_task(
        project_root=Path(project_root) if project_root else Path.cwd(),
        run_id=run_id,
        input_path="__combined_ingest__",
        config=str(config_path) if config_path is not None else None,
        depends_on=depends_on,
    )

def build_report_generate_task(
    *,
    run_id: str,
    project_root: str,
    config_path: object,
    depends_on: list[str],
) -> TaskEvent:
    return build_registered_report_task(
        get_registered_report_task("report.generate"),
        project_root=Path(project_root) if project_root else Path.cwd(),
        run_id=run_id,
        config=str(config_path) if config_path is not None else None,
        depends_on=depends_on,
    )
