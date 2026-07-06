from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from modnews.core.config import load_config
from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent

from .runtime import load_runtime_plan
from .step import PipelinePlanContext, PipelineStepBase
from .task_builder import (
    build_classify_extraction_task,
    build_classify_merge_task,
    build_combine_ingest_task_for_run,
    build_ingest_tasks,
    build_report_generate_task,
)

FollowupBuilder = Callable[[EventQueue, dict[str, Any]], TaskEvent | None]


@dataclass(frozen=True, slots=True)
class FollowupRule:
    trigger: str
    builder: FollowupBuilder
    task_type: str | None = None
    step_prefix: str | None = None

    def matches(self, task: dict[str, Any]) -> bool:
        current_task_type = str(task.get("type") or "")
        current_step_id = str(task.get("step_id") or "")
        if self.task_type is not None and current_task_type != self.task_type:
            return False
        if self.step_prefix is not None and not current_step_id.startswith(self.step_prefix):
            return False
        return True


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
    followup_rules: tuple[FollowupRule, ...] = (
        FollowupRule(
            trigger="ingest_terminal",
            step_prefix="ingest/",
            builder=lambda queue, event: _build_combine_followup_task(queue, event),
        ),
    )

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        return []

    def on_task_completed(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        return _register_followup_for_event(queue, event, self.followup_rules)

    def on_task_failed(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        return _register_followup_for_event(queue, event, self.followup_rules)

    def on_task_blocked(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        return _register_followup_for_event(queue, event, self.followup_rules)


@dataclass(slots=True)
class ClassifyPipelineStep(PipelineStepBase):
    id: str = "pipeline_classify"
    followup_rules: tuple[FollowupRule, ...] = (
        FollowupRule(
            trigger="combine_ingest_completed",
            task_type="pipeline.combine_ingest",
            builder=lambda queue, event: _build_classify_extraction_followup_task(event),
        ),
        FollowupRule(
            trigger="classify_extraction_completed",
            task_type="classify.clustered_event_extraction",
            builder=lambda queue, event: _build_classify_merge_followup_task(event),
        ),
    )

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        return []

    def on_task_completed(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        return _register_followup_for_event(queue, event, self.followup_rules)


@dataclass(slots=True)
class ReportPipelineStep(PipelineStepBase):
    id: str = "pipeline_report"
    followup_rules: tuple[FollowupRule, ...] = (
        FollowupRule(
            trigger="classify_merge_completed",
            task_type="classify.clustered_event_merge",
            builder=lambda queue, event: _build_report_followup_task(event),
        ),
    )

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        return []

    def on_task_completed(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        return _register_followup_for_event(queue, event, self.followup_rules)


def _register_followup_for_event(
    queue: EventQueue | None,
    event: dict[str, Any],
    rules: tuple[FollowupRule, ...],
) -> list[dict[str, Any]]:
    task = _event_task(event)
    if queue is None or not task:
        return []
    for rule in rules:
        if not rule.matches(task):
            continue
        followup = rule.builder(queue, event)
        if followup is None:
            return []
        return _register_task(queue, followup, trigger=rule.trigger)
    return []


def _build_combine_followup_task(queue: EventQueue, event: dict[str, Any]) -> TaskEvent | None:
    task = _event_task(event)
    if not task:
        return None
    run_id = _event_run_id(task)
    project_root = _event_project_root(task)
    if not run_id or not project_root:
        return None
    ingest_task_ids = sorted(
        queued.id
        for queued in queue.list()
        if queued.pipeline_run_id == run_id and queued.step_id and queued.step_id.startswith("ingest/")
    )
    if not ingest_task_ids:
        return None
    return build_combine_ingest_task_for_run(
        run_id=run_id,
        project_root=project_root,
        ingest_task_ids=ingest_task_ids,
    )[0]


def _build_classify_extraction_followup_task(event: dict[str, Any]) -> TaskEvent | None:
    task = _event_task(event)
    if not task:
        return None
    run_id = _event_run_id(task)
    project_root = _event_project_root(task)
    if not run_id or not project_root:
        return None
    config_path = _event_config_path(task)
    if not _classification_enabled(config_path):
        return None
    return build_classify_extraction_task(
        run_id=run_id,
        project_root=project_root,
        config_path=config_path,
        depends_on=[str(task["id"])],
    )


def _build_classify_merge_followup_task(event: dict[str, Any]) -> TaskEvent | None:
    task = _event_task(event)
    if not task:
        return None
    run_id = _event_run_id(task)
    project_root = _event_project_root(task)
    if not run_id or not project_root:
        return None
    config_path = _event_config_path(task)
    if not _classification_enabled(config_path):
        return None
    return build_classify_merge_task(
        run_id=run_id,
        project_root=project_root,
        config_path=config_path,
        depends_on=[str(task["id"])],
    )


def _build_report_followup_task(event: dict[str, Any]) -> TaskEvent | None:
    task = _event_task(event)
    if not task:
        return None
    run_id = _event_run_id(task)
    project_root = _event_project_root(task)
    if not run_id or not project_root:
        return None
    config_path = _event_config_path(task)
    if not _classification_enabled(config_path):
        return None
    return build_report_generate_task(
        run_id=run_id,
        project_root=project_root,
        config_path=config_path,
        depends_on=[str(task["id"])],
    )


def _event_task(event: dict[str, Any]) -> dict[str, Any]:
    return event.get("task") if isinstance(event.get("task"), dict) else {}


def _event_run_id(task: dict[str, Any]) -> str:
    return str(task.get("pipeline_run_id") or "")


def _event_project_root(task: dict[str, Any]) -> str:
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    return str(payload.get("project_root") or "")


def _event_config_path(task: dict[str, Any]) -> str | None:
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    value = payload.get("config")
    if value is None:
        return None
    return str(value)


def _classification_enabled(config_path: str | None) -> bool:
    if not config_path:
        return True
    return bool(load_config(config_path).classification.enabled)


def _register_task(queue: EventQueue, task: TaskEvent, *, trigger: str) -> list[dict[str, Any]]:
    if any(existing.id == task.id for existing in queue.list()):
        return []
    queue.register(task)
    return [
        {
            "action": "register_task",
            "trigger": trigger,
            "task_id": task.id,
            "task_type": task.type,
            "step_id": task.step_id,
            "depends_on": list(task.depends_on),
        }
    ]
