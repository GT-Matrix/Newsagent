from __future__ import annotations

from pathlib import Path

from modnews.core.completion_callbacks import CompletionCallbackRegistry
from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.classify.clustered_tasks import (
    run_clustered_event_extraction_task,
    run_clustered_event_merge_task,
)
from modnews.service.classify.tasks import run_classify_task, run_clustered_pipeline_task
from modnews.service.ingest.tasks import run_ingest_step_task
from modnews.service.extraction.tasks import run_web_source_task
from modnews.service.pipeline.tasks import combine_ingest_task, run_legacy_pipeline_task
from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.outputs import OutputRepository
from modnews.service.pipeline.manager import PipelineManager


def register_completion_callbacks(registry: CompletionCallbackRegistry, pipeline_manager: PipelineManager) -> None:
    registry.register("task.completed", _auto_publish_checkpoint)
    registry.register("task.completed", pipeline_manager.on_task_completed)
    registry.register("task.failed", pipeline_manager.on_task_failed)
    registry.register("task.blocked", pipeline_manager.on_task_blocked)


def register_task_executors(queue: EventQueue) -> None:
    queue.register_executor("diagnostic.echo", _echo)
    queue.register_executor("classify.run_legacy", run_classify_task)
    queue.register_executor("classify.clustered_pipeline", run_clustered_pipeline_task)
    queue.register_executor("classify.clustered_event_extraction", run_clustered_event_extraction_task)
    queue.register_executor("classify.clustered_event_merge", run_clustered_event_merge_task)
    queue.register_executor("ingest.run_step", run_ingest_step_task)
    queue.register_executor("web_source.run", run_web_source_task)
    queue.register_executor("pipeline.combine_ingest", combine_ingest_task)
    queue.register_executor("pipeline.run_legacy", run_legacy_pipeline_task)


def _echo(task: TaskEvent) -> dict[str, object]:
    return {"payload": dict(task.payload)}


def _auto_publish_checkpoint(event: dict[str, object]) -> dict[str, object] | None:
    result = event.get("result")
    task = event.get("task")
    if not isinstance(result, dict) or not isinstance(task, dict):
        return None
    checkpoint_path = result.get("auto_publish_checkpoint")
    project_root = task.get("payload", {}).get("project_root") if isinstance(task.get("payload"), dict) else None
    if not checkpoint_path or not project_root:
        return None
    checkpoint = CheckpointRepository(Path(str(project_root))).read(str(checkpoint_path))
    publish_result = OutputRepository(Path(str(project_root))).publish_from_checkpoint(checkpoint)
    return {"publish": publish_result}
