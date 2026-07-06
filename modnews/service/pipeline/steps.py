from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.core.config import load_config

from .runtime import load_runtime_plan
from .step import PipelinePlanContext, PipelineStepBase
from .task_builder import (
    build_classify_extraction_task,
    build_classify_merge_task,
    build_combine_ingest_task_for_run,
    build_ingest_tasks,
    build_report_generate_task,
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
        return []

    def on_task_completed(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        return _ensure_combine_task(event, queue)

    def on_task_failed(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        return _ensure_combine_task(event, queue)

    def on_task_blocked(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        return _ensure_combine_task(event, queue)


@dataclass(slots=True)
class ClassifyPipelineStep(PipelineStepBase):
    id: str = "pipeline_classify"

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        return []

    def on_task_completed(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        task = _event_task(event)
        if queue is None or not task:
            return []
        task_type = str(task.get("type") or "")
        run_id = _event_run_id(task)
        project_root = _event_project_root(task)
        if not run_id or not project_root:
            return []
        config_path = _event_config_path(task)
        if not _classification_enabled(config_path):
            return []
        if task_type == "pipeline.combine_ingest":
            registered = build_classify_extraction_task(
                run_id=run_id,
                project_root=project_root,
                config_path=config_path,
                depends_on=[str(task["id"])],
            )
            return _register_task(queue, registered, trigger="combine_ingest_completed")
        if task_type == "classify.clustered_event_extraction":
            registered = build_classify_merge_task(
                run_id=run_id,
                project_root=project_root,
                config_path=config_path,
                depends_on=[str(task["id"])],
            )
            return _register_task(queue, registered, trigger="classify_extraction_completed")
        return []


@dataclass(slots=True)
class ReportPipelineStep(PipelineStepBase):
    id: str = "pipeline_report"

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        return []

    def on_task_completed(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        task = _event_task(event)
        if queue is None or not task:
            return []
        if str(task.get("type") or "") != "classify.clustered_event_merge":
            return []
        run_id = _event_run_id(task)
        project_root = _event_project_root(task)
        if not run_id or not project_root:
            return []
        config_path = _event_config_path(task)
        if not _classification_enabled(config_path):
            return []
        registered = build_report_generate_task(
            run_id=run_id,
            project_root=project_root,
            config_path=config_path,
            depends_on=[str(task["id"])],
        )
        return _register_task(queue, registered, trigger="classify_merge_completed")


def _ensure_combine_task(event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]]:
    task = _event_task(event)
    if queue is None or not task:
        return []
    step_id = str(task.get("step_id") or "")
    if not step_id.startswith("ingest/"):
        return []
    run_id = _event_run_id(task)
    project_root = _event_project_root(task)
    if not run_id or not project_root:
        return []
    ingest_task_ids = sorted(
        queued.id
        for queued in queue.list()
        if queued.pipeline_run_id == run_id and queued.step_id and queued.step_id.startswith("ingest/")
    )
    if not ingest_task_ids:
        return []
    registered = build_combine_ingest_task_for_run(
        run_id=run_id,
        project_root=project_root,
        ingest_task_ids=ingest_task_ids,
    )[0]
    return _register_task(queue, registered, trigger="ingest_terminal")


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
