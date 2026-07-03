from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator

SUCCESS_STATES = {"succeeded", "skipped"}
TERMINAL_STATES = {"succeeded", "skipped", "failed", "cancelled", "blocked"}
_CURRENT_TASK: ContextVar["TaskEvent | None"] = ContextVar("modnews_current_task", default=None)


class TaskBlocked(Exception):
    def __init__(self, reason: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}


@dataclass(slots=True)
class TaskEvent:
    id: str
    type: str
    pipeline_run_id: str | None = None
    step_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    concurrency_key: str | None = None
    max_concurrency: int | None = None
    depends_on: list[str] = field(default_factory=list)
    checkpoint_policy: str = "default"
    max_attempts: int = 1
    attempt: int = 0
    state: str = "queued"
    status_reason: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@contextmanager
def task_context(task: TaskEvent) -> Iterator[None]:
    token = _CURRENT_TASK.set(task)
    try:
        yield
    finally:
        _CURRENT_TASK.reset(token)


def current_task() -> TaskEvent | None:
    return _CURRENT_TASK.get()
