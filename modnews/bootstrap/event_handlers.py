from __future__ import annotations

from pathlib import Path

from modnews.core.completion_callbacks import CompletionCallbackRegistry
from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.classify.clustered_tasks import (
    run_clustered_event_extraction_task,
    run_clustered_event_merge_task,
)
from modnews.service.classify.batch_tasks import run_embedding_batch_item
from modnews.service.classify.batch_executor import (
    EventQueueBatchExecutionBackend,
    default_batch_backend,
    execute_registered_batch_item,
)
from modnews.service.ingest.tasks import run_ingest_step_task
from modnews.service.extraction.tasks import run_web_source_task
from modnews.service.extraction.repair_tasks import run_codex_repair_task
from modnews.service.pipeline.tasks import combine_ingest_task
from modnews.service.report.tasks import run_report_generate_task
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
    queue.register_executor("classify.batch_item", execute_registered_batch_item)
    queue.register_executor("classify.embedding", run_embedding_batch_item)
    queue.register_executor(
        "classify.clustered_event_extraction",
        _with_classify_batch_queue(queue, run_clustered_event_extraction_task),
    )
    queue.register_executor("classify.clustered_event_merge", _with_classify_batch_queue(queue, run_clustered_event_merge_task))
    queue.register_executor("ingest.run_step", run_ingest_step_task)
    queue.register_executor("web_source.run", run_web_source_task)
    queue.register_executor("extractor.repair.codex", run_codex_repair_task)
    queue.register_executor("pipeline.combine_ingest", combine_ingest_task)
    queue.register_executor("report.generate", run_report_generate_task)


def _echo(task: TaskEvent) -> dict[str, object]:
    return {"payload": dict(task.payload)}


def _with_classify_batch_queue(queue: EventQueue, executor):
    def wrapped(task: TaskEvent) -> dict[str, object] | None:
        backend = EventQueueBatchExecutionBackend(
            queue,
            run_id=task.pipeline_run_id,
            step_id=task.step_id,
            task_type_prefix="classify.batch_item",
            base_payload=task.payload,
        )
        with default_batch_backend(backend):
            return executor(task)

    return wrapped


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
