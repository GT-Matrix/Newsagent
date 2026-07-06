from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent

from .runtime import load_runtime_plan
from .task_builder import (
    build_classify_tasks,
    build_combine_ingest_task,
    build_ingest_tasks,
    build_report_tasks,
)


@dataclass(slots=True)
class IngestPipelineStep:
    id: str = "pipeline_ingest"

    def plan(self, state: dict[str, Any], completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        if completed_event is not None:
            return []
        request = state.get("request") if isinstance(state.get("request"), dict) else {}
        run_id, project_root, config_path, config = load_runtime_plan(request)
        return build_ingest_tasks(
            project_root=project_root,
            run_id=run_id,
            config_path=config_path,
            config=config,
        )


@dataclass(slots=True)
class CombineIngestPipelineStep:
    id: str = "pipeline_combine_ingest"

    def plan(self, state: dict[str, Any], completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        if completed_event is not None:
            return []
        request = state.get("request") if isinstance(state.get("request"), dict) else {}
        return build_combine_ingest_task(state=state, request=request)


@dataclass(slots=True)
class ClassifyPipelineStep:
    id: str = "pipeline_classify"

    def plan(self, state: dict[str, Any], completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        if completed_event is not None:
            return []
        request = state.get("request") if isinstance(state.get("request"), dict) else {}
        run_id, project_root, config_path, config = load_runtime_plan(request)
        return build_classify_tasks(
            state=state,
            run_id=run_id,
            project_root=project_root,
            config_path=config_path,
            config=config,
        )

    def on_task_completed(self, event: dict[str, Any], queue: EventQueue | None) -> None:
        if queue is None:
            return
        task = event.get("task")
        result = event.get("result")
        if not isinstance(task, dict) or not isinstance(result, dict):
            return
        if task.get("type") != "pipeline.combine_ingest":
            return
        run_id = task.get("pipeline_run_id")
        combined_path = result.get("combined_ingest_path")
        if not run_id or not combined_path:
            return
        for queued_task in queue.list():
            if queued_task.pipeline_run_id != run_id or not queued_task.type.startswith("classify."):
                continue
            queue.patch_payload(queued_task.id, {"input_path": str(combined_path)})


@dataclass(slots=True)
class ReportPipelineStep:
    id: str = "pipeline_report"

    def plan(self, state: dict[str, Any], completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        if completed_event is not None:
            return []
        request = state.get("request") if isinstance(state.get("request"), dict) else {}
        run_id, project_root, config_path, config = load_runtime_plan(request)
        return build_report_tasks(
            state=state,
            run_id=run_id,
            project_root=project_root,
            config_path=config_path,
            config=config,
        )

    def on_task_completed(self, event: dict[str, Any], queue: EventQueue | None) -> None:
        if queue is None:
            return
        task = event.get("task")
        result = event.get("result")
        if not isinstance(task, dict) or not isinstance(result, dict):
            return
        if task.get("type") != "classify.clustered_event_merge":
            return
        run_id = task.get("pipeline_run_id")
        checkpoint_path = result.get("checkpoint_path")
        if not run_id or not checkpoint_path:
            return
        for queued_task in queue.list():
            if queued_task.pipeline_run_id != run_id or queued_task.type != "report.generate":
                continue
            queue.patch_payload(queued_task.id, {"input_path": str(checkpoint_path)})
