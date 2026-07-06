from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.task import TaskEvent
from modnews.service.classify.planner import (
    build_clustered_event_extraction_task,
    build_clustered_event_merge_task,
)
from modnews.service.ingest.planner import plan_ingest_tasks
from modnews.service.pipeline.step import PipelinePlanContext


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


def build_combine_ingest_task(*, context: PipelinePlanContext) -> list[TaskEvent]:
    run_id = context.run_id
    project_root = str(context.request.get("project_root") or "")
    ingest_task_ids = [
        task.id
        for task in context.tasks
        if task.step_id and task.step_id.startswith("ingest/")
    ]
    return build_combine_ingest_task_for_run(
        run_id=run_id,
        project_root=project_root,
        ingest_task_ids=ingest_task_ids,
    )


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


def build_classify_tasks(
    *,
    context: PipelinePlanContext,
    run_id: str,
    project_root: str,
    config_path: object,
    config: Any,
) -> list[TaskEvent]:
    if not config.classification.enabled:
        return []
    combine_task = next((task for task in context.tasks if task.type == "pipeline.combine_ingest"), None)
    if combine_task is None:
        return []
    extraction_task = build_classify_extraction_task(
        run_id=run_id,
        project_root=project_root,
        config_path=config_path,
        depends_on=[combine_task.id],
    )
    merge_task = build_classify_merge_task(
        run_id=run_id,
        project_root=project_root,
        config_path=config_path,
        depends_on=[extraction_task.id],
    )
    return [extraction_task, merge_task]


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


def build_report_tasks(
    *,
    context: PipelinePlanContext,
    run_id: str,
    project_root: str,
    config_path: object,
    config: Any,
) -> list[TaskEvent]:
    if not config.classification.enabled:
        return []
    merge_task = next((task for task in context.tasks if task.type == "classify.clustered_event_merge"), None)
    if merge_task is None:
        return []
    return [
        build_report_generate_task(
            run_id=run_id,
            project_root=project_root,
            config_path=config_path,
            depends_on=[merge_task.id],
        )
    ]


def build_report_generate_task(
    *,
    run_id: str,
    project_root: str,
    config_path: object,
    depends_on: list[str],
) -> TaskEvent:
    return TaskEvent(
        id=f"report-{run_id}-generate",
        type="report.generate",
        pipeline_run_id=run_id,
        step_id="report/generate",
        payload={
            "project_root": project_root,
            "run_id": run_id,
            "config": config_path,
            "input_path": "__latest_classify_checkpoint__",
            "output_dir": "data/output",
        },
        depends_on=depends_on,
        concurrency_key="report",
        max_concurrency=1,
    )
