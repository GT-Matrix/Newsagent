from __future__ import annotations

from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.core.task import TaskEvent


def register_event_handlers(router: EventRouter) -> None:
    """Register default event callbacks.

    The first migration stage keeps legacy execution paths, so no callbacks are
    required yet. New task-based services should register their completion
    handlers here instead of wiring them from route modules.
    """


def register_task_executors(queue: EventQueue) -> None:
    queue.register_executor("diagnostic.echo", _echo)


def _echo(task: TaskEvent) -> dict[str, object]:
    return {"payload": dict(task.payload)}
