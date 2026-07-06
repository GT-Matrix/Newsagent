from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from modnews.core.task import TaskEvent

from .followups import FollowupRule, register_followup_for_event
from .runtime import load_runtime_plan
from .step import PipelineFollowupDescriptor, PipelinePlanContext, PipelineStepBase
from .task_builder import build_ingest_tasks

PipelinePlanner = Callable[[PipelinePlanContext], list[TaskEvent]]


@dataclass(frozen=True, slots=True)
class RegisteredPipelineStepSpec:
    id: str
    title: str
    group: str
    kind: str
    description: str | None = None
    depends_on: tuple[str, ...] = ()
    callback_handlers: tuple[str, ...] = ()
    followup_rules: tuple[FollowupRule, ...] = ()
    concrete_step_ids: tuple[str, ...] = ()
    concrete_step_prefixes: tuple[str, ...] = ()
    planner_id: str | None = None

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
class RegisteredPipelineStep(PipelineStepBase):
    spec: RegisteredPipelineStepSpec

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def title(self) -> str:
        return self.spec.title

    @property
    def group(self) -> str:
        return self.spec.group

    @property
    def kind(self) -> str:
        return self.spec.kind

    @property
    def description(self) -> str | None:
        return self.spec.description

    @property
    def depends_on(self) -> tuple[str, ...]:
        return self.spec.depends_on

    @property
    def callback_handlers(self) -> tuple[str, ...]:
        return self.spec.callback_handlers

    @property
    def followup_descriptors(self) -> tuple[PipelineFollowupDescriptor, ...]:
        return self.spec.followup_descriptors

    @property
    def concrete_step_ids(self) -> tuple[str, ...]:
        return self.spec.concrete_step_ids

    @property
    def concrete_step_prefixes(self) -> tuple[str, ...]:
        return self.spec.concrete_step_prefixes

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        if completed_event is not None or self.spec.planner_id is None:
            return []
        return PIPELINE_PLANNERS[self.spec.planner_id](context)

    def on_task_completed(self, event, queue):
        return self._register_followups("completed", event, queue)

    def on_task_failed(self, event, queue):
        return self._register_followups("failed", event, queue)

    def on_task_blocked(self, event, queue):
        return self._register_followups("blocked", event, queue)

    def _register_followups(self, handler: str, event: dict[str, Any], queue):
        if handler not in self.spec.callback_handlers:
            return None
        return register_followup_for_event(queue, event, self.spec.followup_rules)


def build_ingest_planner_tasks(context: PipelinePlanContext) -> list[TaskEvent]:
    request = context.request
    run_id, project_root, config_path, config = load_runtime_plan(request)
    return build_ingest_tasks(
        project_root=project_root,
        run_id=run_id,
        config_path=config_path,
        config=config,
    )


PIPELINE_PLANNERS: dict[str, PipelinePlanner] = {
    "ingest_root": build_ingest_planner_tasks,
}


REGISTERED_PIPELINE_STEP_SPECS: tuple[RegisteredPipelineStepSpec, ...] = (
    RegisteredPipelineStepSpec(
        id="pipeline_ingest",
        title="Ingest Planner",
        group="ingest",
        kind="root",
        description="负责根据运行配置注册 ingest 入口任务。",
        concrete_step_prefixes=("ingest/",),
        planner_id="ingest_root",
    ),
    RegisteredPipelineStepSpec(
        id="pipeline_combine_ingest",
        title="Combine Ingest Outputs",
        group="ingest",
        kind="followup",
        description="等待 ingest 任务结束后注册合并任务。",
        depends_on=("pipeline_ingest",),
        callback_handlers=("completed", "failed", "blocked"),
        followup_rules=(
            FollowupRule(
                trigger="ingest_terminal",
                step_prefix="ingest/",
                builder_id="combine_ingest_for_run",
            ),
        ),
        concrete_step_ids=("pipeline/combine_ingest",),
    ),
    RegisteredPipelineStepSpec(
        id="pipeline_classify",
        title="Classify Followups",
        group="classify",
        kind="followup",
        description="按统一 followup 规则串联分类抽取与合并任务。",
        depends_on=("pipeline_combine_ingest",),
        callback_handlers=("completed",),
        followup_rules=(
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
        ),
        concrete_step_ids=(
            "classify/clustered_event_extraction",
            "classify/clustered_event_merge",
        ),
    ),
    RegisteredPipelineStepSpec(
        id="pipeline_report",
        title="Report Followups",
        group="report",
        kind="followup",
        description="在分类完成后注册报告生成任务。",
        depends_on=("pipeline_classify",),
        callback_handlers=("completed",),
        followup_rules=(
            FollowupRule(
                trigger="classify_merge_completed",
                task_type="classify.clustered_event_merge",
                builder_id="report_after_classify_merge",
            ),
        ),
        concrete_step_ids=("report/generate",),
    ),
)

REGISTERED_PIPELINE_STEP_SPEC_BY_ID: dict[str, RegisteredPipelineStepSpec] = {
    spec.id: spec
    for spec in REGISTERED_PIPELINE_STEP_SPECS
}


def get_registered_pipeline_step_spec(step_id: str) -> RegisteredPipelineStepSpec:
    return REGISTERED_PIPELINE_STEP_SPEC_BY_ID[step_id]


def build_registered_pipeline_step(step_id: str) -> RegisteredPipelineStep:
    return RegisteredPipelineStep(get_registered_pipeline_step_spec(step_id))


def build_registered_pipeline_steps() -> list[RegisteredPipelineStep]:
    return [RegisteredPipelineStep(spec) for spec in REGISTERED_PIPELINE_STEP_SPECS]
