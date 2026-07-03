from __future__ import annotations

import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .task import TaskEvent

TaskExecutor = Callable[[TaskEvent], dict[str, Any] | None]


@dataclass(slots=True)
class EventQueue:
    _tasks: dict[str, TaskEvent] = field(default_factory=dict)
    _results: dict[str, dict[str, Any]] = field(default_factory=dict)
    _executors: dict[str, TaskExecutor] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def register_executor(self, task_type: str, executor: TaskExecutor) -> None:
        self._executors[task_type] = executor

    def register(self, task: TaskEvent) -> TaskEvent:
        with self._lock:
            self._tasks[task.id] = task
        return task

    def dispatch(self, task: TaskEvent) -> TaskEvent:
        self.register(task)
        return self.run(task.id)

    def run(self, task_id: str) -> TaskEvent:
        with self._lock:
            task = self._tasks[task_id]
            task.state = "running"
        executor = self._executors.get(task.type)
        if not executor:
            with self._lock:
                task.state = "failed"
                self._results[task.id] = {"error": f"no executor registered for {task.type}"}
            return task
        try:
            result = executor(task) or {}
            with self._lock:
                task.state = "succeeded"
                self._results[task.id] = {
                    "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    **result,
                }
        except Exception as exc:
            with self._lock:
                task.state = "failed"
                self._results[task.id] = {"error": str(exc)}
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
