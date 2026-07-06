from __future__ import annotations

from dataclasses import dataclass
from modnews.core.task import TaskEvent

from .followups import FollowupRule, register_followup_for_event
from .runtime import load_runtime_plan
from .step import PipelinePlanContext, PipelineStepBase
from .task_builder import (
    build_ingest_tasks,
)


@dataclass(slots=True)
class FollowupPipelineStepBase(PipelineStepBase):
    followup_rules: tuple[FollowupRule, ...] = ()
    followup_handlers: frozenset[str] = frozenset()

    def on_task_completed(self, event, queue):
        if "completed" not in self.followup_handlers:
            return None
        return register_followup_for_event(queue, event, self.followup_rules)

    def on_task_failed(self, event, queue):
        if "failed" not in self.followup_handlers:
            return None
        return register_followup_for_event(queue, event, self.followup_rules)

    def on_task_blocked(self, event, queue):
        if "blocked" not in self.followup_handlers:
            return None
        return register_followup_for_event(queue, event, self.followup_rules)


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
class CombineIngestPipelineStep(FollowupPipelineStepBase):
    id: str = "pipeline_combine_ingest"
    followup_rules: tuple[FollowupRule, ...] = (
        FollowupRule(
            trigger="ingest_terminal",
            step_prefix="ingest/",
            builder_id="combine_ingest_for_run",
        ),
    )
    followup_handlers: frozenset[str] = frozenset({"completed", "failed", "blocked"})

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        return []


@dataclass(slots=True)
class ClassifyPipelineStep(FollowupPipelineStepBase):
    id: str = "pipeline_classify"
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
    followup_handlers: frozenset[str] = frozenset({"completed"})

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        return []


@dataclass(slots=True)
class ReportPipelineStep(FollowupPipelineStepBase):
    id: str = "pipeline_report"
    followup_rules: tuple[FollowupRule, ...] = (
        FollowupRule(
            trigger="classify_merge_completed",
            task_type="classify.clustered_event_merge",
            builder_id="report_after_classify_merge",
        ),
    )
    followup_handlers: frozenset[str] = frozenset({"completed"})

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        return []
