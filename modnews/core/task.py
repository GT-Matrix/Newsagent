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

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TaskEvent":
        return cls(
            id=str(raw["id"]),
            type=str(raw["type"]),
            pipeline_run_id=str(raw["pipeline_run_id"]) if raw.get("pipeline_run_id") is not None else None,
            step_id=str(raw["step_id"]) if raw.get("step_id") is not None else None,
            payload=dict(raw.get("payload") or {}),
            concurrency_key=str(raw["concurrency_key"]) if raw.get("concurrency_key") is not None else None,
            max_concurrency=int(raw["max_concurrency"]) if raw.get("max_concurrency") is not None else None,
            depends_on=[str(item) for item in raw.get("depends_on") or []],
            checkpoint_policy=str(raw.get("checkpoint_policy") or "default"),
            max_attempts=int(raw.get("max_attempts") or 1),
            attempt=int(raw.get("attempt") or 0),
            state=str(raw.get("state") or "queued"),
            status_reason=str(raw["status_reason"]) if raw.get("status_reason") is not None else None,
            created_at=str(raw["created_at"]) if raw.get("created_at") is not None else None,
            started_at=str(raw["started_at"]) if raw.get("started_at") is not None else None,
            finished_at=str(raw["finished_at"]) if raw.get("finished_at") is not None else None,
        )


@contextmanager
def task_context(task: TaskEvent) -> Iterator[None]:
    token = _CURRENT_TASK.set(task)
    try:
        yield
    finally:
        _CURRENT_TASK.reset(token)


def current_task() -> TaskEvent | None:
    return _CURRENT_TASK.get()
