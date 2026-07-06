from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modnews.core.config import apply_runtime_overrides, load_config
from modnews.core.task import TaskEvent
from modnews.service.ingest.planner import plan_ingest_tasks


def load_runtime_plan(request: dict[str, Any]) -> tuple[str, str, object, Any]:
    run_id = str(request.get("run_id") or "local")
    project_root = str(request.get("project_root") or "")
    config_path = request.get("config")
    config = load_config(config_path, project_root=project_root)
    apply_runtime_overrides(
        config,
        only_ingest_steps=request.get("only_ingest_steps") or request.get("only"),
        disable_classification=bool(request.get("disable_classification")),
    )
    return run_id, project_root, config_path, config


@dataclass(slots=True)
class IngestPipelineStep:
    id: str = "pipeline_ingest"

    def plan(self, state: dict[str, Any], completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        if completed_event is not None:
            return []
        request = state.get("request") if isinstance(state.get("request"), dict) else {}
        run_id, project_root, config_path, config = load_runtime_plan(request)
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


@dataclass(slots=True)
class CombineIngestPipelineStep:
    id: str = "pipeline_combine_ingest"

    def plan(self, state: dict[str, Any], completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        request = state.get("request") if isinstance(state.get("request"), dict) else {}
        run_id = str(state.get("run_id") or request.get("run_id") or "local")
        project_root = str(request.get("project_root") or "")
        if completed_event is not None:
            return []
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


@dataclass(slots=True)
class ClassifyPipelineStep:
    id: str = "pipeline_classify"

    def plan(self, state: dict[str, Any], completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        request = state.get("request") if isinstance(state.get("request"), dict) else {}
        run_id, project_root, config_path, config = load_runtime_plan(request)
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
        if completed_event is not None:
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


@dataclass(slots=True)
class ReportPipelineStep:
    id: str = "pipeline_report"

    def plan(self, state: dict[str, Any], completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        request = state.get("request") if isinstance(state.get("request"), dict) else {}
        run_id, project_root, config_path, config = load_runtime_plan(request)
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
        if completed_event is not None:
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
