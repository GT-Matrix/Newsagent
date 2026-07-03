from __future__ import annotations

import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .events import EventRouter
from .task import TERMINAL_STATES, TaskEvent

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
        with self._lock:
            task = self._tasks[task_id]
            blocked_reason = self._blocked_reason(task, dict(self._tasks))
            if blocked_reason:
                task.state = "blocked"
                self._results[task.id] = {"blocked_reason": blocked_reason}
                return task
            task.state = "running"
            task.started_at = _now()
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
        except Exception as exc:
            with self._lock:
                task.state = "failed"
                task.finished_at = _now()
                self._results[task.id] = {"error": str(exc)}
            self._dispatch("task.failed", task)
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

    def status(self) -> dict[str, int]:
        with self._lock:
            return dict(Counter(task.state for task in self._tasks.values()))

    def blocked_reason(self, task: TaskEvent) -> str | None:
        with self._lock:
            tasks = dict(self._tasks)
        return self._blocked_reason(task, tasks)

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
        with self._lock:
            tasks = dict(self._tasks)
            for task in tasks.values():
                reason = self._blocked_reason(task, tasks)
                if task.state == "queued" and reason:
                    task.state = "blocked"
                    self._results[task.id] = {"blocked_reason": reason}

    def _is_ready(self, task: TaskEvent, tasks: dict[str, TaskEvent]) -> bool:
        return task.state in {"queued", "blocked"} and self._blocked_reason(task, tasks) is None

    def _blocked_reason(self, task: TaskEvent, tasks: dict[str, TaskEvent]) -> str | None:
        for dependency_id in task.depends_on:
            dependency = tasks.get(dependency_id)
            if dependency is None:
                return f"missing dependency {dependency_id}"
            if dependency.state != "succeeded":
                if dependency.state in TERMINAL_STATES:
                    return f"dependency {dependency_id} ended as {dependency.state}"
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


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
