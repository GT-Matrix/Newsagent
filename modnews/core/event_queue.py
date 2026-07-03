from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field

from .task import TaskEvent


@dataclass(slots=True)
class EventQueue:
    _tasks: dict[str, TaskEvent] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def register(self, task: TaskEvent) -> TaskEvent:
        with self._lock:
            self._tasks[task.id] = task
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

    def status(self) -> dict[str, int]:
        with self._lock:
            return dict(Counter(task.state for task in self._tasks.values()))
