from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modnews.core.task import TaskEvent

from .runtime import load_runtime_plan
from .step import PipelinePlanContext, PipelineStepBase
from .task_builder import (
    build_classify_tasks,
    build_combine_ingest_task,
    build_ingest_tasks,
    build_report_tasks,
)


@dataclass(slots=True)
class IngestPipelineStep(PipelineStepBase):
    id: str = "pipeline_ingest"

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        if completed_event is not None:
            return []
        request = context.request
        run_id, project_root, config_path, config = load_runtime_plan(request)
        return build_ingest_tasks(
            project_root=project_root,
            run_id=run_id,
            config_path=config_path,
            config=config,
        )


@dataclass(slots=True)
class CombineIngestPipelineStep(PipelineStepBase):
    id: str = "pipeline_combine_ingest"

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        if completed_event is not None:
            return []
        return build_combine_ingest_task(context=context)


@dataclass(slots=True)
class ClassifyPipelineStep(PipelineStepBase):
    id: str = "pipeline_classify"

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        if completed_event is not None:
            return []
        request = context.request
        run_id, project_root, config_path, config = load_runtime_plan(request)
        return build_classify_tasks(
            context=context,
            run_id=run_id,
            project_root=project_root,
            config_path=config_path,
            config=config,
        )


@dataclass(slots=True)
class ReportPipelineStep(PipelineStepBase):
    id: str = "pipeline_report"

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        if completed_event is not None:
            return []
        request = context.request
        run_id, project_root, config_path, config = load_runtime_plan(request)
        return build_report_tasks(
            context=context,
            run_id=run_id,
            project_root=project_root,
            config_path=config_path,
            config=config,
        )
