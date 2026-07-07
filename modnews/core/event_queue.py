from __future__ import annotations

import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Iterator

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
    parse_ts,
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

_CURRENT_QUEUE: ContextVar["EventQueue | None"] = ContextVar("modnews_current_queue", default=None)


@contextmanager
def queue_context(queue: "EventQueue") -> Iterator[None]:
    token = _CURRENT_QUEUE.set(queue)
    try:
        yield
    finally:
        _CURRENT_QUEUE.reset(token)


def current_queue() -> "EventQueue | None":
    return _CURRENT_QUEUE.get()


@dataclass(slots=True)
class EventQueue:
    _tasks: dict[str, TaskEvent] = field(default_factory=dict)
    _results: dict[str, dict[str, Any]] = field(default_factory=dict)
    _transient_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    _executors: dict[str, TaskExecutor] = field(default_factory=dict)
    _loggers: list[TaskLogger] = field(default_factory=list)
    _state_writer: TaskStateWriter | None = None
    _router: EventRouter | None = None
    _run_index: dict[str, set[str]] = field(default_factory=dict)
    _group_index: dict[str, set[str]] = field(default_factory=dict)
    _parent_index: dict[str, set[str]] = field(default_factory=dict)
    _dependency_index: dict[str, set[str]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _drain_state: threading.local = field(default_factory=threading.local)

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
            self._transient_results = {}
            self._rebuild_indexes()
        self._persist_snapshot()

    def register(self, task: TaskEvent) -> TaskEvent:
        with self._lock:
            if task.created_at is None:
                task.created_at = now()
            existing = self._tasks.get(task.id)
            if existing is not None:
                self._unindex_task(existing)
            self._tasks[task.id] = task
            self._index_task(task)
            self._persist_task(task)
        self._log(task, "task.registered")
        return task

    def register_many(self, tasks: list[TaskEvent]) -> list[TaskEvent]:
        if not tasks:
            return []
        with self._lock:
            for task in tasks:
                if task.created_at is None:
                    task.created_at = now()
                existing = self._tasks.get(task.id)
                if existing is not None:
                    self._unindex_task(existing)
                self._tasks[task.id] = task
                self._index_task(task)
            self._persist_tasks(tasks)
        for task in tasks:
            self._log(task, "task.registered")
        return tasks

    def submit(self, task: TaskEvent) -> TaskEvent:
        self.register(task)
        self.drain_ready()
        return task

    def dispatch(self, task: TaskEvent) -> TaskEvent:
        self.submit(task)
        return self.get(task.id)

    def drain_ready(self, *, limit: int | None = None) -> list[TaskEvent]:
        if self._is_draining():
            return []
        self._set_draining(True)
        ran: list[TaskEvent] = []
        executor: ThreadPoolExecutor | None = None
        in_flight: dict[Future[TaskEvent], str] = {}
        try:
            while True:
                remaining = None if limit is None else max(0, limit - len(ran) - len(in_flight))
                if remaining == 0:
                    break
                claimed = self._claim_ready_tasks(limit=remaining)
                if claimed and executor is None:
                    executor = ThreadPoolExecutor(max_workers=self._suggest_worker_count(claimed))
                for task in claimed:
                    ran.append(task)
                    assert executor is not None
                    future = executor.submit(self._run_claimed, task.id)
                    in_flight[future] = task.id
                if not in_flight:
                    self._mark_blocked()
                    break
                done, _ = wait(tuple(in_flight), return_when=FIRST_COMPLETED)
                for future in done:
                    in_flight.pop(future, None)
                    future.result()
            return ran
        finally:
            if executor is not None:
                executor.shutdown(wait=True)
            self._set_draining(False)

    def run(self, task_id: str) -> TaskEvent:
        blocked_before_run = False
        should_execute = False
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
                self._persist_task(task)
                self._log(task, "task.waiting", reason=current_waiting_reason)
                return task
            if not blocked_before_run:
                mark_task_running(task)
                self._persist_task(task)
                self._log(task, "task.started")
                should_execute = True
        if blocked_before_run:
            self._persist_task(task)
            self._dispatch("task.blocked", task)
            if not self._is_draining():
                self.drain_ready()
            return task
        if should_execute:
            self._execute_running_task(task)
        return task

    def _run_claimed(self, task_id: str) -> TaskEvent:
        task = self.get(task_id)
        self._execute_running_task(task)
        return self.get(task_id)

    def _execute_running_task(self, task: TaskEvent) -> None:
        executor = self._executors.get(task.type)
        if not executor:
            with self._lock:
                mark_task_failed(task, self._results, f"no executor registered for {task.type}")
                self._persist_task(task)
                self._log(task, "task.failed", error=self._results[task.id]["error"])
            self._dispatch("task.failed", task)
            if not self._is_draining():
                self.drain_ready()
            return
        try:
            with queue_context(self):
                with task_context(task):
                    result = executor(task) or {}
            with self._lock:
                persisted_result = self._persistable_result(task, result)
                mark_task_succeeded(task, self._results, persisted_result)
                transient_result = self._transient_result(task, result, persisted_result)
                if transient_result:
                    self._transient_results[task.id] = transient_result
                else:
                    self._transient_results.pop(task.id, None)
                self._persist_task(task)
                self._log(task, "task.completed", result_keys=sorted(self._results[task.id].keys()))
            self._dispatch("task.completed", task)
            if not self._is_draining():
                self.drain_ready()
        except TaskBlocked as exc:
            with self._lock:
                mark_task_blocked(task, self._results, exc.reason, details=exc.details)
                self._persist_task(task)
                self._log(task, "task.blocked", reason=exc.reason)
            self._dispatch("task.blocked", task)
            if not self._is_draining():
                self.drain_ready()
        except Exception as exc:
            with self._lock:
                if task.attempt < max(1, task.max_attempts):
                    mark_task_retry_scheduled(task, self._results, str(exc))
                    self._persist_task(task)
                    self._log(task, "task.retry_scheduled", error=str(exc))
                    event_type = "task.retry_scheduled"
                else:
                    mark_task_failed(task, self._results, str(exc))
                    self._persist_task(task)
                    self._log(task, "task.failed", error=str(exc))
                    event_type = "task.failed"
            self._dispatch(event_type, task)
            if not self._is_draining():
                self.drain_ready()

    def list(self, states: set[str] | None = None) -> list[TaskEvent]:
        with self._lock:
            tasks = list(self._tasks.values())
        if states:
            tasks = [task for task in tasks if task.state in states]
        return tasks

    def list_by_run(self, run_id: str, states: set[str] | None = None) -> list[TaskEvent]:
        with self._lock:
            ids = list(self._run_index.get(run_id, set()))
            tasks = [self._tasks[task_id] for task_id in ids if task_id in self._tasks]
        if states:
            tasks = [task for task in tasks if task.state in states]
        return sorted(tasks, key=lambda task: (task.created_at or "", task.id))

    def get(self, task_id: str) -> TaskEvent:
        with self._lock:
            return self._tasks[task_id]

    def result(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            result = dict(self._results.get(task_id, {}))
            transient = self._transient_results.get(task_id)
            if isinstance(transient, dict):
                result.update(transient)
            return result

    def inspect_tasks(self, tasks: list[TaskEvent]) -> dict[str, dict[str, Any]]:
        with self._lock:
            tasks_snapshot = snapshot_tasks(self._tasks)
            results = {task_id: dict(result) for task_id, result in self._results.items()}
            transient_results = {task_id: dict(result) for task_id, result in self._transient_results.items()}
        running_by_concurrency: dict[str, int] = {}
        for item in tasks_snapshot.values():
            if item.state == "running" and item.concurrency_key:
                running_by_concurrency[item.concurrency_key] = running_by_concurrency.get(item.concurrency_key, 0) + 1
        inspected: dict[str, dict[str, Any]] = {}
        for task in tasks:
            result = dict(results.get(task.id, {}))
            transient = transient_results.get(task.id)
            if transient:
                result.update(transient)
            waiting = self._inspect_waiting_details(task, tasks_snapshot, running_by_concurrency)
            blocked = self._inspect_blocked_details(task, result, tasks_snapshot)
            waiting_reason_value = self._waiting_reason_from_details(waiting)
            blocked_reason_value = None
            if task.state == "blocked":
                blocked_reason_value = result.get("blocked_reason") or task.status_reason
                if not blocked_reason_value and blocked:
                    blocked_reason_value = f"dependency {blocked.get('dependency_id')} ended as {blocked.get('dependency_state')}"
            inspected[task.id] = {
                "result": result,
                "waiting_details": waiting,
                "waiting_reason": waiting_reason_value,
                "blocked_details": dict(blocked) if isinstance(blocked, dict) else None,
                "blocked_reason": str(blocked_reason_value) if blocked_reason_value else None,
                "ready": waiting is None and task.state in {"queued", "waiting"},
            }
        return inspected

    def collect_task_results(
        self,
        task_ids: list[str],
        *,
        value_key: str | None = None,
        consume: bool = False,
    ) -> list[dict[str, Any]] | list[Any]:
        with self._lock:
            values: list[dict[str, Any]] | list[Any] = []
            for task_id in task_ids:
                merged = dict(self._results.get(task_id, {}))
                transient = self._transient_results.get(task_id)
                if isinstance(transient, dict):
                    merged.update(transient)
                values.append(merged[value_key] if value_key is not None else merged)
            if consume:
                for task_id in task_ids:
                    self._transient_results.pop(task_id, None)
        return values

    def set_transient_result(self, task_id: str, payload: dict[str, Any], *, merge: bool = True) -> None:
        with self._lock:
            if task_id not in self._tasks:
                raise KeyError(task_id)
            if merge:
                current = self._transient_results.setdefault(task_id, {})
                current.update(payload)
            else:
                self._transient_results[task_id] = dict(payload)

    def discard_transient_results(self, task_ids: list[str]) -> None:
        with self._lock:
            for task_id in task_ids:
                self._transient_results.pop(task_id, None)

    def patch_payload(self, task_id: str, patch: dict[str, Any]) -> TaskEvent:
        with self._lock:
            task = self._tasks[task_id]
            task.payload.update(patch)
            self._persist_task(task)
            return task

    def cancel(self, task_id: str, *, reason: str = "cancelled") -> TaskEvent:
        with self._lock:
            task = self._tasks[task_id]
            if task.state in TERMINAL_STATES:
                return task
            if task.state == "running":
                self._results[task.id] = {"error": "cannot cancel running task", "cancel_reason": reason}
                self._persist_task(task)
                return task
            mark_task_cancelled(task, self._results, reason)
            self._persist_task(task)
            self._log(task, "task.cancelled", reason=reason)
            return task

    def retry(self, task_id: str) -> TaskEvent:
        with self._lock:
            task = self._tasks[task_id]
            if task.state not in {"failed", "cancelled", "blocked"}:
                return task
            reset_task_for_retry(task, self._results)
            self._persist_task(task)
            self._log(task, "task.retry_requested")
            return task

    def skip(self, task_id: str, *, reason: str = "skipped") -> TaskEvent:
        with self._lock:
            task = self._tasks[task_id]
            if task.state in {"succeeded", "skipped"}:
                return task
            if task.state == "running":
                self._results[task.id] = {"error": "cannot skip running task", "skip_reason": reason}
                self._persist_task(task)
                return task
            mark_task_skipped(task, self._results, reason)
            released = unblock_released_tasks(self._tasks, self._results, dependency_task_id=task_id)
            self._persist_tasks([task, *released])
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
            ids = sorted(self._dependency_index.get(task_id, set()))
            return [self._tasks[item] for item in ids if item in self._tasks]

    def children_of(self, task_id: str) -> list[TaskEvent]:
        with self._lock:
            ids = sorted(self._parent_index.get(task_id, set()))
            return [self._tasks[item] for item in ids if item in self._tasks]

    def group_members(self, task_group_id: str) -> list[TaskEvent]:
        with self._lock:
            ids = sorted(self._group_index.get(task_group_id, set()))
            return [self._tasks[item] for item in ids if item in self._tasks]

    def group_summary(self, task_group_id: str) -> dict[str, Any]:
        with self._lock:
            ids = sorted(self._group_index.get(task_group_id, set()))
            members = [self._tasks[item] for item in ids if item in self._tasks]
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

    def _inspect_waiting_details(
        self,
        task: TaskEvent,
        tasks: dict[str, TaskEvent],
        running_by_concurrency: dict[str, int],
    ) -> dict[str, Any] | None:
        retry_at = parse_ts(task.next_attempt_at)
        current = parse_ts(now()) if retry_at is not None else None
        if retry_at is not None and current is not None and retry_at > current:
            return {"kind": "retry_window", "next_attempt_at": task.next_attempt_at}
        for dependency_id in task.depends_on:
            dependency = tasks.get(dependency_id)
            if dependency is None:
                continue
            if dependency.state not in SUCCESS_STATES:
                if dependency.state in TERMINAL_STATES:
                    continue
                return {
                    "kind": "dependency",
                    "dependency_id": dependency_id,
                    "dependency_state": dependency.state,
                }
        if task.concurrency_key and task.max_concurrency:
            running = running_by_concurrency.get(task.concurrency_key, 0)
            if task.state == "running":
                running = max(0, running - 1)
            if running >= task.max_concurrency:
                return {
                    "kind": "concurrency",
                    "concurrency_key": task.concurrency_key,
                    "max_concurrency": task.max_concurrency,
                    "running_count": running,
                }
        return None

    def _inspect_blocked_details(
        self,
        task: TaskEvent,
        result: dict[str, Any],
        tasks: dict[str, TaskEvent],
    ) -> dict[str, Any] | None:
        if task.state != "blocked":
            return None
        details = result.get("blocked_details")
        if isinstance(details, dict):
            return dict(details)
        return dependency_blocked_details(task, tasks)

    def _waiting_reason_from_details(self, details: dict[str, Any] | None) -> str | None:
        if not details:
            return None
        kind = details.get("kind")
        if kind == "retry_window":
            return f"waiting until retry window {details.get('next_attempt_at')}"
        if kind == "dependency":
            return f"waiting for dependency {details.get('dependency_id')}"
        if kind == "concurrency":
            return f"waiting for concurrency slot {details.get('concurrency_key')}"
        return None

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
            tasks_snapshot = snapshot_tasks(self._tasks)
            tasks = list(tasks_snapshot.values())
        for task in tasks:
            details = waiting_details(task, tasks_snapshot)
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
            tasks_snapshot = snapshot_tasks(self._tasks)
            tasks = list(tasks_snapshot.values())
        for task in tasks:
            result = self.result(task.id)
            details = result.get("blocked_details")
            if not isinstance(details, dict) and task.state == "blocked":
                details = dependency_blocked_details(task, tasks_snapshot)
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
            tasks_snapshot = snapshot_tasks(self._tasks)
            tasks = list(tasks_snapshot.values())
        for task in tasks:
            details = waiting_details(task, tasks_snapshot)
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
                    current_task = self._tasks.get(task.id)
                    if current_task is not None:
                        self._persist_task(current_task)

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
            self._persist_tasks([task for task, _reason in waiting_tasks] + blocked_tasks)
            for task, reason in waiting_tasks:
                self._log(task, "task.waiting", reason=reason)
            for task in blocked_tasks:
                self._log(task, "task.blocked", reason=self._results[task.id]["blocked_reason"])
        for task in blocked_tasks:
            self._dispatch("task.blocked", task)

    def _persistable_result(self, task: TaskEvent, result: dict[str, Any]) -> dict[str, Any]:
        if task.checkpoint_policy != "none":
            return result
        persisted = dict(result)
        for key in ("batch_result",):
            persisted.pop(key, None)
        return persisted

    def _transient_result(
        self,
        task: TaskEvent,
        result: dict[str, Any],
        persisted_result: dict[str, Any],
    ) -> dict[str, Any]:
        if task.checkpoint_policy != "none":
            return {}
        return {key: value for key, value in result.items() if key not in persisted_result}

    def _claim_ready_tasks(self, *, limit: int | None = None) -> list[TaskEvent]:
        claimed: list[TaskEvent] = []
        with self._lock:
            tasks = snapshot_tasks(self._tasks)
            ready = [task for task in tasks.values() if is_ready(task, tasks)]
            ready.sort(key=lambda task: (task.priority, task.created_at or "", task.id))
            for task in ready:
                if limit is not None and len(claimed) >= limit:
                    break
                if not is_ready(task, tasks):
                    continue
                mark_task_running(task)
                claimed.append(task)
                tasks[task.id] = task
            if claimed:
                self._persist_tasks(claimed)
        for task in claimed:
            self._log(task, "task.started")
        return claimed

    def _suggest_worker_count(self, claimed: list[TaskEvent] | None = None) -> int:
        candidates = claimed or []
        if not candidates:
            with self._lock:
                tasks = snapshot_tasks(self._tasks)
            candidates = [task for task in tasks.values() if is_ready(task, tasks)]
        if not candidates:
            return 1
        unconstrained = sum(1 for task in candidates if not task.max_concurrency)
        constrained = sum(max(1, int(task.max_concurrency or 1)) for task in candidates if task.max_concurrency)
        return max(1, min(64, unconstrained + constrained))

    def _is_draining(self) -> bool:
        return bool(getattr(self._drain_state, "active", False))

    def _set_draining(self, active: bool) -> None:
        self._drain_state.active = active

    def _rebuild_indexes(self) -> None:
        self._run_index = {}
        self._group_index = {}
        self._parent_index = {}
        self._dependency_index = {}
        for task in self._tasks.values():
            self._index_task(task)

    def _index_task(self, task: TaskEvent) -> None:
        if task.pipeline_run_id:
            self._run_index.setdefault(task.pipeline_run_id, set()).add(task.id)
        if task.task_group_id:
            self._group_index.setdefault(task.task_group_id, set()).add(task.id)
        if task.parent_task_id:
            self._parent_index.setdefault(task.parent_task_id, set()).add(task.id)
        for dependency_id in task.depends_on:
            self._dependency_index.setdefault(dependency_id, set()).add(task.id)

    def _unindex_task(self, task: TaskEvent) -> None:
        self._discard_index_value(self._run_index, task.pipeline_run_id, task.id)
        self._discard_index_value(self._group_index, task.task_group_id, task.id)
        self._discard_index_value(self._parent_index, task.parent_task_id, task.id)
        for dependency_id in task.depends_on:
            self._discard_index_value(self._dependency_index, dependency_id, task.id)

    def _discard_index_value(self, index: dict[str, set[str]], key: str | None, task_id: str) -> None:
        if not key:
            return
        values = index.get(key)
        if values is None:
            return
        values.discard(task_id)
        if not values:
            index.pop(key, None)

    def _log(self, task: TaskEvent, event_type: str, **payload: Any) -> None:
        for logger in list(self._loggers):
            try:
                logger(task, event_type, payload)
            except Exception:
                pass

    def _persist_task(self, task: TaskEvent) -> None:
        writer = self._state_writer
        if writer is None:
            return
        try:
            writer(
                {
                    "op": "upsert",
                    "saved_at": now(),
                    "task": task.to_dict(),
                    "result": dict(self._results.get(task.id, {})),
                }
            )
        except Exception:
            pass

    def _persist_tasks(self, tasks: list[TaskEvent]) -> None:
        if not tasks:
            return
        writer = self._state_writer
        if writer is None:
            return
        try:
            writer(
                {
                    "op": "upsert_many",
                    "saved_at": now(),
                    "tasks": [task.to_dict() for task in tasks],
                    "results": {task.id: dict(self._results.get(task.id, {})) for task in tasks},
                }
            )
        except Exception:
            pass

    def _persist_snapshot(self) -> None:
        writer = self._state_writer
        if writer is None:
            return
        try:
            writer({"op": "replace", **self.snapshot()})
        except Exception:
            pass
