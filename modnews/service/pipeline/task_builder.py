from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.task import TaskEvent
from modnews.service.ingest.planner import plan_ingest_tasks


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


def build_combine_ingest_task(*, state: dict[str, Any], request: dict[str, Any]) -> list[TaskEvent]:
    run_id = str(state.get("run_id") or request.get("run_id") or "local")
    project_root = str(request.get("project_root") or "")
    ingest_task_ids = [
        task.id
        for task in state.get("tasks", [])
        if isinstance(task, TaskEvent) and task.step_id and task.step_id.startswith("ingest/")
    ]
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
    state: dict[str, Any],
    run_id: str,
    project_root: str,
    config_path: object,
    config: Any,
) -> list[TaskEvent]:
    if not config.classification.enabled:
        return []
    combine_task = next(
        (
            task
            for task in state.get("tasks", [])
            if isinstance(task, TaskEvent) and task.type == "pipeline.combine_ingest"
        ),
        None,
    )
    if combine_task is None:
        return []
    extraction_task = TaskEvent(
        id=f"classify-{run_id}-clustered-event-extraction",
        type="classify.clustered_event_extraction",
        pipeline_run_id=run_id,
        step_id="classify/clustered_event_extraction",
        payload={
            "project_root": project_root,
            "run_id": run_id,
            "config": config_path,
            "input_path": "__combined_ingest__",
        },
        depends_on=[combine_task.id],
        concurrency_key="classify",
        max_concurrency=1,
    )
    merge_task = TaskEvent(
        id=f"classify-{run_id}-clustered-event-merge",
        type="classify.clustered_event_merge",
        pipeline_run_id=run_id,
        step_id="classify/clustered_event_merge",
        payload={
            "project_root": project_root,
            "run_id": run_id,
            "config": config_path,
            "input_path": "__combined_ingest__",
        },
        depends_on=[extraction_task.id],
        concurrency_key="classify",
        max_concurrency=1,
    )
    return [extraction_task, merge_task]


def build_report_tasks(
    *,
    state: dict[str, Any],
    run_id: str,
    project_root: str,
    config_path: object,
    config: Any,
) -> list[TaskEvent]:
    if not config.classification.enabled:
        return []
    merge_task = next(
        (
            task
            for task in state.get("tasks", [])
            if isinstance(task, TaskEvent) and task.type == "classify.clustered_event_merge"
        ),
        None,
    )
    if merge_task is None:
        return []
    return [
        TaskEvent(
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
            depends_on=[merge_task.id],
            concurrency_key="report",
            max_concurrency=1,
        )
    ]
