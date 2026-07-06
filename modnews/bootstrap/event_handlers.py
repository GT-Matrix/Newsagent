from __future__ import annotations

from pathlib import Path
from datetime import datetime

from modnews.core.completion_callbacks import CompletionCallbackRegistry
from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.classify.task_execution import (
    run_clustered_event_extraction_task,
    run_clustered_event_merge_task,
)
from modnews.service.classify.planner import build_clustered_event_merge_task
from modnews.service.classify.batch_tasks import (
    run_clustered_event_extraction_batch_item,
    run_clustered_event_merge_batch_item,
    run_embedding_batch_item,
    run_relevance_batch_item,
)
from modnews.service.classify.batch_executor import (
    EventQueueBatchExecutionBackend,
    default_batch_backend,
)
from modnews.service.ingest.tasks import run_ingest_step_task
from modnews.service.extraction.tasks import run_web_source_task
from modnews.service.extraction.repair_tasks import run_codex_repair_task
from modnews.service.extraction.repair_queue import build_repair_task_event
from modnews.service.pipeline.tasks import combine_ingest_task
from modnews.service.report.tasks import run_report_generate_task
from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.outputs import OutputRepository
from modnews.service.pipeline.manager import PipelineManager


def register_completion_callbacks(registry: CompletionCallbackRegistry, pipeline_manager: PipelineManager) -> None:
    registry.register("task.completed", _auto_publish_checkpoint)
    registry.register("task.completed", _auto_schedule_classify_followup(pipeline_manager.event_queue))
    registry.register("task.completed", pipeline_manager.on_task_completed)
    registry.register("task.failed", pipeline_manager.on_task_failed)
    registry.register("task.blocked", pipeline_manager.on_task_blocked)
    registry.register("task.blocked", _auto_queue_blocked_web_source_repair(pipeline_manager.event_queue))


def register_task_executors(queue: EventQueue) -> None:
    queue.register_executor("diagnostic.echo", _echo)
    queue.register_executor("classify.embedding", run_embedding_batch_item)
    queue.register_executor("classify.batch_relevance", run_relevance_batch_item)
    queue.register_executor("classify.clustered_event_extraction.batch", run_clustered_event_extraction_batch_item)
    queue.register_executor("classify.clustered_event_merge.batch", run_clustered_event_merge_batch_item)
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


def _auto_queue_blocked_web_source_repair(queue: EventQueue | None):
    def callback(event: dict[str, object]) -> dict[str, object] | None:
        if queue is None:
            return None
        task = event.get("task")
        result = event.get("result")
        if not isinstance(task, dict) or not isinstance(result, dict):
            return None
        if task.get("type") != "web_source.run":
            return None
        task_id = str(task.get("id") or "")
        source_id = str(
            result.get("job", {}).get("source_id")
            if isinstance(result.get("job"), dict)
            else task.get("payload", {}).get("source_id") if isinstance(task.get("payload"), dict) else ""
        )
        repair_task_id = result.get("repair_task_id")
        if repair_task_id and source_id and not _has_repair_queue_task(queue, str(repair_task_id)):
            payload = task.get("payload", {}) if isinstance(task.get("payload"), dict) else {}
            project_root = Path(str(payload.get("project_root") or Path.cwd())).resolve()
            repair_task = build_repair_task_event(
                project_root=project_root,
                repair_task_id=str(repair_task_id),
                source_id=source_id,
                run_id=str(task.get("pipeline_run_id") or "") or None,
                task_id=f"repair-{repair_task_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            )
            queue.submit(repair_task)
        if task_id and queue.get(task_id).state == "blocked":
            queue.skip(task_id, reason=str(result.get("blocked_reason") or "blocked web source safely skipped"))
        return None

    return callback


def _auto_schedule_classify_followup(queue: EventQueue | None):
    def callback(event: dict[str, object]) -> dict[str, object] | None:
        if queue is None:
            return None
        task = event.get("task")
        if not isinstance(task, dict):
            return None
        if task.get("type") != "classify.clustered_event_extraction":
            return None
        run_id = str(task.get("pipeline_run_id") or "")
        payload = task.get("payload", {}) if isinstance(task.get("payload"), dict) else {}
        if not run_id:
            return None
        merge_id = f"classify-{run_id}-clustered-event-merge"
        if any(existing.id == merge_id for existing in queue.list()):
            return None
        project_root = Path(str(payload.get("project_root") or Path.cwd())).resolve()
        merge_task = build_clustered_event_merge_task(
            project_root=project_root,
            run_id=run_id,
            input_path=payload.get("input_path") if isinstance(payload.get("input_path"), str) else None,
            config=payload.get("config") if isinstance(payload.get("config"), str) else None,
            depends_on=[str(task.get("id") or "")],
        )
        queue.register(merge_task)
        return {
            "classify_followup": {
                "action": "register_task",
                "task_id": merge_task.id,
                "task_type": merge_task.type,
                "depends_on": list(merge_task.depends_on),
            }
        }

    return callback


def _has_repair_queue_task(queue: EventQueue, repair_task_id: str) -> bool:
    return any(
        task.type == "extractor.repair.codex"
        and task.payload.get("repair_task_id") == repair_task_id
        and task.state not in {"cancelled", "failed"}
        for task in queue.list()
    )
