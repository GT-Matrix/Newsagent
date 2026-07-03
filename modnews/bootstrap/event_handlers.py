from __future__ import annotations

from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.core.task import TaskEvent
from modnews.internal.service.classify.tasks import run_classify_task
from modnews.internal.service.ingest.tasks import run_ingest_step_task
from modnews.internal.service.extraction.tasks import run_web_source_task
from modnews.internal.service.pipeline.tasks import run_legacy_pipeline_task


def register_event_handlers(router: EventRouter) -> None:
    """Register default event callbacks.

    The first migration stage keeps legacy execution paths, so no callbacks are
    required yet. New task-based services should register their completion
    handlers here instead of wiring them from route modules.
    """


def register_task_executors(queue: EventQueue) -> None:
    queue.register_executor("diagnostic.echo", _echo)
    queue.register_executor("classify.run_legacy", run_classify_task)
    queue.register_executor("ingest.run_step", run_ingest_step_task)
    queue.register_executor("web_source.run", run_web_source_task)
    queue.register_executor("pipeline.run_legacy", run_legacy_pipeline_task)


def _echo(task: TaskEvent) -> dict[str, object]:
    return {"payload": dict(task.payload)}
