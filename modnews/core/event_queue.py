from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .events import EventRouter
from .event_queue_support import (
    blocked_tasks_to_mark,
    dependency_blocked_details,
    dependency_blocked_reason,
    is_ready,
    mark_task_blocked,
    mark_task_cancelled,
    mark_task_failed,
    mark_task_retry_scheduled,
    mark_task_running,
    mark_task_skipped,
    mark_task_succeeded,
    mark_task_waiting,
    next_ready_task,
    now,
    reset_task_for_retry,
    snapshot_tasks,
    status_counts,
    unblock_released_tasks,
    waiting_details,
    waiting_reason,
)
from .task import SUCCESS_STATES, TERMINAL_STATES, TaskBlocked, TaskEvent, task_context

TaskExecutor = Callable[[TaskEvent], dict[str, Any] | None]
TaskLogger = Callable[[TaskEvent, str, dict[str, Any]], None]
TaskStateWriter = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class EventQueue:
    _tasks: dict[str, TaskEvent] = field(default_factory=dict)
    _results: dict[str, dict[str, Any]] = field(default_factory=dict)
    _executors: dict[str, TaskExecutor] = field(default_factory=dict)
    _loggers: list[TaskLogger] = field(default_factory=list)
    _state_writer: TaskStateWriter | None = None
    _router: EventRouter | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def bind_router(self, router: EventRouter) -> None:
        self._router = router

    def register_executor(self, task_type: str, executor: TaskExecutor) -> None:
        self._executors[task_type] = executor

    def unregister_executor(self, task_type: str) -> None:
        self._executors.pop(task_type, None)

    def bind_logger(self, logger: TaskLogger) -> None:
        self._loggers.append(logger)

    def bind_state_writer(self, writer: TaskStateWriter) -> None:
        self._state_writer = writer

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "version": 1,
                "saved_at": now(),
                "tasks": [task.to_dict() for task in self._tasks.values()],
                "results": {task_id: dict(result) for task_id, result in self._results.items()},
            }

    def load_snapshot(self, payload: dict[str, Any]) -> None:
        tasks: dict[str, TaskEvent] = {}
        results: dict[str, dict[str, Any]] = {}
        for raw in payload.get("tasks", []):
            if not isinstance(raw, dict) or not raw.get("id") or not raw.get("type"):
                continue
            task = TaskEvent.from_dict(raw)
            if task.state == "running" and task.recovery_policy == "requeue_running":
                task.state = "queued"
                task.status_reason = "restored from interrupted running state"
                task.started_at = None
                task.finished_at = None
                restored = dict(payload.get("results", {}).get(task.id, {})) if isinstance(payload.get("results"), dict) else {}
                restored["restored_from"] = "running"
                results[task.id] = restored
            elif task.state == "running" and task.recovery_policy == "fail_running":
                task.state = "failed"
                task.status_reason = "restored interrupted running task as failed"
                task.finished_at = now()
                restored = dict(payload.get("results", {}).get(task.id, {})) if isinstance(payload.get("results"), dict) else {}
                restored["restored_from"] = "running"
                restored["error"] = "restored interrupted running task as failed"
                results[task.id] = restored
            else:
                if isinstance(payload.get("results"), dict):
                    result = payload["results"].get(task.id)
                    if isinstance(result, dict):
                        results[task.id] = dict(result)
            tasks[task.id] = task
        with self._lock:
            self._tasks = tasks
            self._results = results
        self._persist()

    def register(self, task: TaskEvent) -> TaskEvent:
        with self._lock:
            if task.created_at is None:
                task.created_at = now()
            self._tasks[task.id] = task
        self._persist()
        self._log(task, "task.registered")
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
            tasks_snapshot = snapshot_tasks(self._tasks)
            blocked_reason = dependency_blocked_reason(task, tasks_snapshot)
            if blocked_reason:
                mark_task_blocked(task, self._results, blocked_reason, details=dependency_blocked_details(task, tasks_snapshot))
                self._log(task, "task.blocked", reason=blocked_reason)
                blocked_before_run = True
            current_waiting_reason = waiting_reason(task, tasks_snapshot)
            if not blocked_before_run and current_waiting_reason:
                mark_task_waiting(task, self._results, current_waiting_reason)
                self._persist()
                self._log(task, "task.waiting", reason=current_waiting_reason)
                return task
            if not blocked_before_run:
                mark_task_running(task)
                self._persist()
                self._log(task, "task.started")
        if blocked_before_run:
            self._persist()
            self._dispatch("task.blocked", task)
            self.drain_ready()
            return task
        executor = self._executors.get(task.type)
        if not executor:
            with self._lock:
                mark_task_failed(task, self._results, f"no executor registered for {task.type}")
                self._persist()
                self._log(task, "task.failed", error=self._results[task.id]["error"])
            self._dispatch("task.failed", task)
            self.drain_ready()
            return task
        try:
            with task_context(task):
                result = executor(task) or {}
            with self._lock:
                mark_task_succeeded(task, self._results, result)
                self._persist()
                self._log(task, "task.completed", result_keys=sorted(self._results[task.id].keys()))
            self._dispatch("task.completed", task)
            self.drain_ready()
        except TaskBlocked as exc:
            with self._lock:
                mark_task_blocked(task, self._results, exc.reason, details=exc.details)
                self._persist()
                self._log(task, "task.blocked", reason=exc.reason)
            self._dispatch("task.blocked", task)
            self.drain_ready()
        except Exception as exc:
            with self._lock:
                if task.attempt < max(1, task.max_attempts):
                    mark_task_retry_scheduled(task, self._results, str(exc))
                    self._persist()
                    self._log(task, "task.retry_scheduled", error=str(exc))
                    event_type = "task.retry_scheduled"
                else:
                    mark_task_failed(task, self._results, str(exc))
                    self._persist()
                    self._log(task, "task.failed", error=str(exc))
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
            self._persist()
            return task

    def cancel(self, task_id: str, *, reason: str = "cancelled") -> TaskEvent:
        with self._lock:
            task = self._tasks[task_id]
            if task.state in TERMINAL_STATES:
                return task
            if task.state == "running":
                self._results[task.id] = {"error": "cannot cancel running task", "cancel_reason": reason}
                self._persist()
                return task
            mark_task_cancelled(task, self._results, reason)
            self._persist()
            self._log(task, "task.cancelled", reason=reason)
            return task

    def retry(self, task_id: str) -> TaskEvent:
        with self._lock:
            task = self._tasks[task_id]
            if task.state not in {"failed", "cancelled", "blocked"}:
                return task
            reset_task_for_retry(task, self._results)
            self._persist()
            self._log(task, "task.retry_requested")
            return task

    def skip(self, task_id: str, *, reason: str = "skipped") -> TaskEvent:
        with self._lock:
            task = self._tasks[task_id]
            if task.state in {"succeeded", "skipped"}:
                return task
            if task.state == "running":
                self._results[task.id] = {"error": "cannot skip running task", "skip_reason": reason}
                self._persist()
                return task
            mark_task_skipped(task, self._results, reason)
            released = unblock_released_tasks(self._tasks, self._results, dependency_task_id=task_id)
            self._persist()
            self._log(task, "task.skipped", reason=reason)
            for dependent in released:
                self._log(dependent, "task.unblocked", dependency=task_id)
        self._dispatch("task.skipped", task)
        for dependent in released:
            self._dispatch("task.unblocked", dependent)
        self.drain_ready()
        return task

    def dependents_of(self, task_id: str) -> list[TaskEvent]:
        with self._lock:
            return [task for task in self._tasks.values() if task_id in task.depends_on]

    def children_of(self, task_id: str) -> list[TaskEvent]:
        with self._lock:
            return [task for task in self._tasks.values() if task.parent_task_id == task_id]

    def group_members(self, task_group_id: str) -> list[TaskEvent]:
        with self._lock:
            return [task for task in self._tasks.values() if task.task_group_id == task_group_id]

    def group_summary(self, task_group_id: str) -> dict[str, Any]:
        members = self.group_members(task_group_id)
        by_state = self._group_state_counts(members)
        return {
            "task_group_id": task_group_id,
            "size": len(members),
            "by_state": by_state,
            "active": sum(by_state.get(state, 0) for state in ("queued", "waiting", "running")),
            "terminal": sum(by_state.get(state, 0) for state in TERMINAL_STATES),
            "succeeded": by_state.get("succeeded", 0),
            "failed": by_state.get("failed", 0) + by_state.get("cancelled", 0),
            "blocked": by_state.get("blocked", 0),
            "member_ids": [task.id for task in members],
        }

    def _group_state_counts(self, members: list[TaskEvent]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for task in members:
            counts[task.state] = counts.get(task.state, 0) + 1
        return dict(sorted(counts.items()))

    def status(self) -> dict[str, int]:
        with self._lock:
            return status_counts(self._tasks)

    def waiting_reason(self, task: TaskEvent) -> str | None:
        with self._lock:
            tasks = snapshot_tasks(self._tasks)
        return waiting_reason(task, tasks)

    def waiting_details(self, task: TaskEvent) -> dict[str, Any] | None:
        with self._lock:
            tasks = snapshot_tasks(self._tasks)
        details = waiting_details(task, tasks)
        return dict(details) if isinstance(details, dict) else None

    def waiting_groups(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {
            "retry_window": [],
            "dependency": [],
            "concurrency": [],
        }
        with self._lock:
            tasks = list(self._tasks.values())
        for task in tasks:
            details = self.waiting_details(task)
            if not details:
                continue
            kind = str(details.get("kind") or "")
            if kind in groups:
                groups[kind].append(task.id)
        return groups

    def blocked_reason(self, task: TaskEvent) -> str | None:
        if task.state == "blocked":
            result = self.result(task.id)
            reason = result.get("blocked_reason") or task.status_reason
            if reason:
                return str(reason)
            with self._lock:
                tasks = snapshot_tasks(self._tasks)
            inferred = dependency_blocked_reason(task, tasks)
            if inferred:
                return inferred
        return None

    def blocked_details(self, task: TaskEvent) -> dict[str, Any] | None:
        if task.state != "blocked":
            return None
        result = self.result(task.id)
        details = result.get("blocked_details")
        if isinstance(details, dict):
            return dict(details)
        with self._lock:
            tasks = snapshot_tasks(self._tasks)
        dependency_details = dependency_blocked_details(task, tasks)
        return dict(dependency_details) if isinstance(dependency_details, dict) else None

    def blocked_groups(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {
            "dependency": [],
            "business": [],
        }
        with self._lock:
            tasks = list(self._tasks.values())
        for task in tasks:
            details = self.blocked_details(task)
            if not details:
                continue
            kind = str(details.get("kind") or "business")
            if kind not in groups:
                kind = "business"
            groups[kind].append(task.id)
        return groups

    def next_retry_at(self) -> str | None:
        candidates: list[str] = []
        with self._lock:
            tasks = list(self._tasks.values())
        for task in tasks:
            details = self.waiting_details(task)
            if not details or details.get("kind") != "retry_window":
                continue
            candidate = details.get("next_attempt_at")
            if isinstance(candidate, str) and candidate:
                candidates.append(candidate)
        return min(candidates) if candidates else None

    def ready(self) -> list[TaskEvent]:
        with self._lock:
            tasks = snapshot_tasks(self._tasks)
        return [task for task in tasks.values() if is_ready(task, tasks)]

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
            tasks = snapshot_tasks(self._tasks)
        ready = [task for task in tasks.values() if is_ready(task, tasks)]
        if not ready:
            return None
        ready.sort(key=lambda task: (task.priority, task.created_at or "", task.id))
        return ready[0]

    def _mark_blocked(self) -> None:
        blocked_tasks: list[TaskEvent]
        with self._lock:
            blocked_tasks, waiting_tasks = blocked_tasks_to_mark(self._tasks, self._results)
            self._persist()
            for task, reason in waiting_tasks:
                self._log(task, "task.waiting", reason=reason)
            for task in blocked_tasks:
                self._log(task, "task.blocked", reason=self._results[task.id]["blocked_reason"])
        for task in blocked_tasks:
            self._dispatch("task.blocked", task)

    def _log(self, task: TaskEvent, event_type: str, **payload: Any) -> None:
        for logger in list(self._loggers):
            try:
                logger(task, event_type, payload)
            except Exception:
                pass

    def _persist(self) -> None:
        writer = self._state_writer
        if writer is None:
            return
        try:
            writer(self.snapshot())
        except Exception:
            pass
