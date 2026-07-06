from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modnews.core.task import TaskEvent

from .followups import FollowupRule, register_followup_for_event
from .runtime import load_runtime_plan
from .step import PipelineFollowupDescriptor, PipelinePlanContext, PipelineStepBase
from .task_builder import (
    build_ingest_tasks,
)


@dataclass(slots=True)
class FollowupPipelineStepBase(PipelineStepBase):
    kind: str = "followup"
    followup_rules: tuple[FollowupRule, ...] = ()
    callback_handlers: tuple[str, ...] = ()

    def on_task_completed(self, event, queue):
        if "completed" not in self.callback_handlers:
            return None
        return register_followup_for_event(queue, event, self.followup_rules)

    def on_task_failed(self, event, queue):
        if "failed" not in self.callback_handlers:
            return None
        return register_followup_for_event(queue, event, self.followup_rules)

    def on_task_blocked(self, event, queue):
        if "blocked" not in self.callback_handlers:
            return None
        return register_followup_for_event(queue, event, self.followup_rules)

    @property
    def followup_descriptors(self) -> tuple[PipelineFollowupDescriptor, ...]:
        return tuple(
            PipelineFollowupDescriptor(
                trigger=rule.trigger,
                builder_id=rule.builder_id,
                task_type=rule.task_type,
                step_prefix=rule.step_prefix,
            )
            for rule in self.followup_rules
        )


@dataclass(slots=True)
class IngestPipelineStep(PipelineStepBase):
    id: str = "pipeline_ingest"
    title: str = "Ingest Planner"
    group: str = "ingest"
    description: str = "负责根据运行配置注册 ingest 入口任务。"

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
class CombineIngestPipelineStep(FollowupPipelineStepBase):
    id: str = "pipeline_combine_ingest"
    title: str = "Combine Ingest Outputs"
    group: str = "ingest"
    description: str = "等待 ingest 任务结束后注册合并任务。"
    followup_rules: tuple[FollowupRule, ...] = (
        FollowupRule(
            trigger="ingest_terminal",
            step_prefix="ingest/",
            builder_id="combine_ingest_for_run",
        ),
    )
    callback_handlers: tuple[str, ...] = ("completed", "failed", "blocked")

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        return []


@dataclass(slots=True)
class ClassifyPipelineStep(FollowupPipelineStepBase):
    id: str = "pipeline_classify"
    title: str = "Classify Followups"
    group: str = "classify"
    description: str = "按统一 followup 规则串联分类抽取与合并任务。"
    followup_rules: tuple[FollowupRule, ...] = (
        FollowupRule(
            trigger="combine_ingest_completed",
            task_type="pipeline.combine_ingest",
            builder_id="classify_extraction_after_combine",
        ),
        FollowupRule(
            trigger="classify_extraction_completed",
            task_type="classify.clustered_event_extraction",
            builder_id="classify_merge_after_extraction",
        ),
    )
    callback_handlers: tuple[str, ...] = ("completed",)

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        return []


@dataclass(slots=True)
class ReportPipelineStep(FollowupPipelineStepBase):
    id: str = "pipeline_report"
    title: str = "Report Followups"
    group: str = "report"
    description: str = "在分类完成后注册报告生成任务。"
    followup_rules: tuple[FollowupRule, ...] = (
        FollowupRule(
            trigger="classify_merge_completed",
            task_type="classify.clustered_event_merge",
            builder_id="report_after_classify_merge",
        ),
    )
    callback_handlers: tuple[str, ...] = ("completed",)

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        return []
