from __future__ import annotations

from pathlib import Path

from modnews.core.completion_callbacks import CompletionCallbackRegistry
from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.classify.extraction_node_runtime import handle_clustered_event_extraction_callback
from modnews.service.classify.merge_node_runtime import handle_clustered_event_merge_callback
from modnews.service.classify.task_execution import REGISTERED_CLASSIFY_TASK_EXECUTORS
from modnews.service.classify.batch_task_registry import REGISTERED_BATCH_TASKS
from modnews.service.classify.batch_executor import (
    EventQueueBatchExecutionBackend,
    default_batch_backend,
)
from modnews.service.ingest.tasks import REGISTERED_INGEST_TASK_EXECUTORS
from modnews.service.extraction.tasks import REGISTERED_EXTRACTION_TASK_EXECUTORS
from modnews.service.extraction.web_source_node_runtime import handle_web_source_child_task_callback
from modnews.service.extraction.repair_tasks import REGISTERED_REPAIR_TASK_EXECUTORS
from modnews.service.extraction.repair_queue_runtime import handle_blocked_web_source_event
from modnews.service.pipeline.tasks import REGISTERED_PIPELINE_TASK_EXECUTORS
from modnews.service.report.node_runtime import handle_report_child_task_callback
from modnews.service.report.tasks import REGISTERED_REPORT_TASK_EXECUTORS
from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.outputs import OutputRepository
from modnews.service.pipeline.manager import PipelineManager


def register_completion_callbacks(registry: CompletionCallbackRegistry, pipeline_manager: PipelineManager) -> None:
    registry.register("task.completed", _auto_publish_checkpoint)
    registry.register("task.completed", _handle_classify_child_task_callback(pipeline_manager.event_queue))
    registry.register("task.blocked", _handle_classify_child_task_callback(pipeline_manager.event_queue))
    registry.register("task.failed", _handle_classify_child_task_callback(pipeline_manager.event_queue))
    registry.register("task.completed", pipeline_manager.on_task_completed)
    registry.register("task.failed", pipeline_manager.on_task_failed)
    registry.register("task.blocked", pipeline_manager.on_task_blocked)
    registry.register("task.blocked", _auto_queue_blocked_web_source_repair(pipeline_manager.event_queue))


def register_task_executors(queue: EventQueue) -> None:
    queue.register_executor("diagnostic.echo", _echo)
    for spec in REGISTERED_BATCH_TASKS:
        queue.register_executor(spec.task_type, spec.executor)
    for task_type, executor in REGISTERED_CLASSIFY_TASK_EXECUTORS.items():
        queue.register_executor(task_type, _with_classify_batch_queue(queue, executor))
    for task_type, executor in REGISTERED_INGEST_TASK_EXECUTORS.items():
        queue.register_executor(task_type, executor)
    for task_type, executor in REGISTERED_EXTRACTION_TASK_EXECUTORS.items():
        queue.register_executor(task_type, executor)
    for task_type, executor in REGISTERED_REPAIR_TASK_EXECUTORS.items():
        queue.register_executor(task_type, executor)
    for task_type, executor in REGISTERED_PIPELINE_TASK_EXECUTORS.items():
        queue.register_executor(task_type, executor)
    for task_type, executor in REGISTERED_REPORT_TASK_EXECUTORS.items():
        queue.register_executor(task_type, executor)


def _echo(task: TaskEvent) -> dict[str, object]:
    return {"payload": dict(task.payload)}


def _with_classify_batch_queue(queue: EventQueue, executor):
    def wrapped(task: TaskEvent) -> dict[str, object] | None:
        backend = EventQueueBatchExecutionBackend(
            queue,
            run_id=task.pipeline_run_id,
            step_id=task.step_id,
            base_payload=task.payload,
            base_task=task,
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


def _auto_queue_blocked_web_source_repair(queue: EventQueue | None):
    def callback(event: dict[str, object]) -> dict[str, object] | None:
        if queue is None:
            return None
        return handle_blocked_web_source_event(queue, event)

    return callback


def _handle_classify_child_task_callback(queue: EventQueue | None):
    def callback(event: dict[str, object]) -> dict[str, object] | None:
        decisions = [
            *handle_clustered_event_extraction_callback(event, queue),
            *handle_clustered_event_merge_callback(event, queue),
            *handle_report_child_task_callback(event, queue),
            *handle_web_source_child_task_callback(event, queue),
        ]
        if not decisions:
            return None
        return {"classify_callback_decisions": decisions}

    return callback
