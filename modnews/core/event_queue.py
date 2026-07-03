from __future__ import annotations

import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .events import EventRouter
from .task import TERMINAL_STATES, TaskBlocked, TaskEvent

TaskExecutor = Callable[[TaskEvent], dict[str, Any] | None]


@dataclass(slots=True)
class EventQueue:
    _tasks: dict[str, TaskEvent] = field(default_factory=dict)
    _results: dict[str, dict[str, Any]] = field(default_factory=dict)
    _executors: dict[str, TaskExecutor] = field(default_factory=dict)
    _router: EventRouter | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def bind_router(self, router: EventRouter) -> None:
        self._router = router

    def register_executor(self, task_type: str, executor: TaskExecutor) -> None:
        self._executors[task_type] = executor

    def unregister_executor(self, task_type: str) -> None:
        self._executors.pop(task_type, None)

    def register(self, task: TaskEvent) -> TaskEvent:
        with self._lock:
            if task.created_at is None:
                task.created_at = _now()
            self._tasks[task.id] = task
        return task

    def submit(self, task: TaskEvent) -> TaskEvent:
        self.register(task)
        self.drain_ready()
        return task

    def dispatch(self, task: TaskEvent) -> TaskEvent:
        self.submit(task)
        return self.get(task.id)

    def drain_ready(self, *, limit: int | None = None) -> list[TaskEvent]:
        ran: list[TaskEvent] = []
        while limit is None or len(ran) < limit:
            task = self._next_ready()
            if task is None:
                self._mark_blocked()
                break
            ran.append(self.run(task.id))
        return ran

    def run(self, task_id: str) -> TaskEvent:
        blocked_before_run = False
        with self._lock:
            task = self._tasks[task_id]
            blocked_reason = self._dependency_blocked_reason(task, dict(self._tasks))
            if blocked_reason:
                self._block_task(task, blocked_reason)
                blocked_before_run = True
            waiting_reason = self._waiting_reason(task, dict(self._tasks))
            if not blocked_before_run and waiting_reason:
                task.state = "waiting"
                task.status_reason = waiting_reason
                self._results[task.id] = {"waiting_reason": waiting_reason}
                return task
            if not blocked_before_run:
                task.state = "running"
                task.status_reason = None
                task.attempt += 1
                task.started_at = _now()
        if blocked_before_run:
            self._dispatch("task.blocked", task)
            self.drain_ready()
            return task
        executor = self._executors.get(task.type)
        if not executor:
            with self._lock:
                task.state = "failed"
                task.finished_at = _now()
                self._results[task.id] = {"error": f"no executor registered for {task.type}"}
            self._dispatch("task.failed", task)
            self.drain_ready()
            return task
        try:
            result = executor(task) or {}
            with self._lock:
                task.state = "succeeded"
                task.finished_at = _now()
                self._results[task.id] = {
                    "finished_at": task.finished_at,
                    **result,
                }
            self._dispatch("task.completed", task)
            self.drain_ready()
        except TaskBlocked as exc:
            with self._lock:
                self._block_task(task, exc.reason, exc.details)
            self._dispatch("task.blocked", task)
            self.drain_ready()
        except Exception as exc:
            with self._lock:
                task.finished_at = _now()
                if task.attempt < max(1, task.max_attempts):
                    task.state = "queued"
                    task.status_reason = f"retry scheduled after attempt {task.attempt}"
                    self._results[task.id] = {
                        "error": str(exc),
                        "attempt": task.attempt,
                        "max_attempts": task.max_attempts,
                        "retry_scheduled": True,
                    }
                    event_type = "task.retry_scheduled"
                else:
                    task.state = "failed"
                    task.status_reason = str(exc)
                    self._results[task.id] = {
                        "error": str(exc),
                        "attempt": task.attempt,
                        "max_attempts": task.max_attempts,
                    }
                    event_type = "task.failed"
            self._dispatch(event_type, task)
            self.drain_ready()
        return task

    def list(self, states: set[str] | None = None) -> list[TaskEvent]:
        with self._lock:
            tasks = list(self._tasks.values())
        if states:
            tasks = [task for task in tasks if task.state in states]
        return tasks

    def get(self, task_id: str) -> TaskEvent:
        with self._lock:
            return self._tasks[task_id]

    def result(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._results.get(task_id, {}))

    def patch_payload(self, task_id: str, patch: dict[str, Any]) -> TaskEvent:
        with self._lock:
            task = self._tasks[task_id]
            task.payload.update(patch)
            return task

    def cancel(self, task_id: str, *, reason: str = "cancelled") -> TaskEvent:
        with self._lock:
            task = self._tasks[task_id]
            if task.state in TERMINAL_STATES:
                return task
            if task.state == "running":
                self._results[task.id] = {"error": "cannot cancel running task", "cancel_reason": reason}
                return task
            task.state = "cancelled"
            task.finished_at = _now()
            self._results[task.id] = {"cancel_reason": reason}
            return task

    def retry(self, task_id: str) -> TaskEvent:
        with self._lock:
            task = self._tasks[task_id]
            if task.state not in {"failed", "cancelled", "blocked"}:
                return task
            task.state = "queued"
            task.status_reason = None
            task.started_at = None
            task.finished_at = None
            task.attempt = 0
            self._results.pop(task.id, None)
            return task

    def dependents_of(self, task_id: str) -> list[TaskEvent]:
        with self._lock:
            return [task for task in self._tasks.values() if task_id in task.depends_on]

    def status(self) -> dict[str, int]:
        with self._lock:
            return dict(Counter(task.state for task in self._tasks.values()))

    def waiting_reason(self, task: TaskEvent) -> str | None:
        with self._lock:
            tasks = dict(self._tasks)
        return self._waiting_reason(task, tasks)

    def blocked_reason(self, task: TaskEvent) -> str | None:
        if task.state == "blocked":
            result = self.result(task.id)
            reason = result.get("blocked_reason") or task.status_reason
            return str(reason) if reason else None
        return None

    def ready(self) -> list[TaskEvent]:
        with self._lock:
            tasks = dict(self._tasks)
        return [task for task in tasks.values() if self._is_ready(task, tasks)]

    def _dispatch(self, event_type: str, task: TaskEvent) -> None:
        if self._router:
            patches = self._router.dispatch(event_type, {"task": task.to_dict(), "result": self.result(task.id)})
            if patches:
                with self._lock:
                    current = self._results.setdefault(task.id, {})
                    for patch in patches:
                        current.update(patch)

    def _next_ready(self) -> TaskEvent | None:
        with self._lock:
            tasks = dict(self._tasks)
        for task in tasks.values():
            if self._is_ready(task, tasks):
                return task
        return None

    def _mark_blocked(self) -> None:
        blocked_tasks: list[TaskEvent] = []
        with self._lock:
            tasks = dict(self._tasks)
            for task in tasks.values():
                blocked_reason = self._dependency_blocked_reason(task, tasks)
                if task.state in {"queued", "waiting"} and blocked_reason:
                    self._block_task(task, blocked_reason)
                    blocked_tasks.append(task)
                    continue
                reason = self._waiting_reason(task, tasks)
                if task.state == "queued" and reason:
                    task.state = "waiting"
                    task.status_reason = reason
                    self._results[task.id] = {"waiting_reason": reason}
        for task in blocked_tasks:
            self._dispatch("task.blocked", task)

    def _is_ready(self, task: TaskEvent, tasks: dict[str, TaskEvent]) -> bool:
        return (
            task.state in {"queued", "waiting"}
            and self._dependency_blocked_reason(task, tasks) is None
            and self._waiting_reason(task, tasks) is None
        )

    def _waiting_reason(self, task: TaskEvent, tasks: dict[str, TaskEvent]) -> str | None:
        for dependency_id in task.depends_on:
            dependency = tasks.get(dependency_id)
            if dependency is None:
                continue
            if dependency.state != "succeeded":
                if dependency.state in TERMINAL_STATES:
                    continue
                return f"waiting for dependency {dependency_id}"
        if task.concurrency_key and task.max_concurrency:
            running = sum(
                1
                for other in tasks.values()
                if other.id != task.id
                and other.state == "running"
                and other.concurrency_key == task.concurrency_key
            )
            if running >= task.max_concurrency:
                return f"waiting for concurrency slot {task.concurrency_key}"
        return None

    def _dependency_blocked_reason(self, task: TaskEvent, tasks: dict[str, TaskEvent]) -> str | None:
        for dependency_id in task.depends_on:
            dependency = tasks.get(dependency_id)
            if dependency is None:
                return f"missing dependency {dependency_id}"
            if dependency.state in TERMINAL_STATES and dependency.state != "succeeded":
                return f"dependency {dependency_id} ended as {dependency.state}"
        return None

    def _block_task(self, task: TaskEvent, reason: str, details: dict[str, Any] | None = None) -> None:
        task.state = "blocked"
        task.status_reason = reason
        task.finished_at = _now()
        self._results[task.id] = {"blocked_reason": reason, **(details or {})}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
