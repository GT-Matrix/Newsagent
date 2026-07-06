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
from modnews.service.pipeline.task_registry import (
    build_registered_pipeline_task,
    get_registered_pipeline_task,
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
        build_registered_pipeline_task(
            get_registered_pipeline_task("pipeline.combine_ingest"),
            project_root=Path(project_root) if project_root else Path.cwd(),
            run_id=run_id,
            depends_on=ingest_task_ids,
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
        input_path=None,
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
        input_path=None,
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
