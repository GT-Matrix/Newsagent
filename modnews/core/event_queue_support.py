from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from .task import SUCCESS_STATES, TERMINAL_STATES, TaskEvent


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def snapshot_tasks(tasks: dict[str, TaskEvent]) -> dict[str, TaskEvent]:
    return dict(tasks)


def status_counts(tasks: dict[str, TaskEvent]) -> dict[str, int]:
    return dict(Counter(task.state for task in tasks.values()))


def dependency_blocked_reason(task: TaskEvent, tasks: dict[str, TaskEvent]) -> str | None:
    for dependency_id in task.depends_on:
        dependency = tasks.get(dependency_id)
        if dependency is None:
            return f"missing dependency {dependency_id}"
        if dependency.state in TERMINAL_STATES and dependency.state not in SUCCESS_STATES:
            return f"dependency {dependency_id} ended as {dependency.state}"
    return None


def waiting_details(task: TaskEvent, tasks: dict[str, TaskEvent]) -> dict[str, Any] | None:
    retry_at = parse_ts(task.next_attempt_at)
    if retry_at is not None:
        current = parse_ts(now())
        if current is not None and retry_at > current:
            return {
                "kind": "retry_window",
                "next_attempt_at": task.next_attempt_at,
            }
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
        running = sum(
            1
            for other in tasks.values()
            if other.id != task.id
            and other.state == "running"
            and other.concurrency_key == task.concurrency_key
        )
        if running >= task.max_concurrency:
            return {
                "kind": "concurrency",
                "concurrency_key": task.concurrency_key,
                "max_concurrency": task.max_concurrency,
                "running_count": running,
            }
    return None


def waiting_reason(task: TaskEvent, tasks: dict[str, TaskEvent]) -> str | None:
    details = waiting_details(task, tasks)
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


def is_ready(task: TaskEvent, tasks: dict[str, TaskEvent]) -> bool:
    return (
        task.state in {"queued", "waiting"}
        and dependency_blocked_reason(task, tasks) is None
        and waiting_reason(task, tasks) is None
    )


def next_ready_task(tasks: dict[str, TaskEvent]) -> TaskEvent | None:
    for task in tasks.values():
        if is_ready(task, tasks):
            return task
    return None


def mark_task_blocked(
    task: TaskEvent,
    results: dict[str, dict[str, Any]],
    reason: str,
    *,
    details: dict[str, Any] | None = None,
) -> None:
    task.state = "blocked"
    task.status_reason = reason
    task.finished_at = now()
    results[task.id] = {"blocked_reason": reason, **(details or {})}


def mark_task_waiting(
    task: TaskEvent,
    results: dict[str, dict[str, Any]],
    reason: str,
) -> None:
    task.state = "waiting"
    task.status_reason = reason
    results[task.id] = {**results.get(task.id, {}), "waiting_reason": reason}


def mark_task_running(task: TaskEvent) -> None:
    task.state = "running"
    task.status_reason = None
    task.next_attempt_at = None
    task.attempt += 1
    task.started_at = now()


def mark_task_succeeded(
    task: TaskEvent,
    results: dict[str, dict[str, Any]],
    result: dict[str, Any],
) -> None:
    task.state = "succeeded"
    task.finished_at = now()
    results[task.id] = {"finished_at": task.finished_at, **result}


def mark_task_retry_scheduled(
    task: TaskEvent,
    results: dict[str, dict[str, Any]],
    error: str,
) -> None:
    delay_seconds = max(0, task.retry_backoff_seconds)
    task.finished_at = now()
    task.state = "queued"
    task.next_attempt_at = None
    if delay_seconds > 0:
        retry_at = datetime.now().astimezone() + timedelta(seconds=delay_seconds)
        task.next_attempt_at = retry_at.isoformat(timespec="seconds")
    task.status_reason = f"retry scheduled after attempt {task.attempt}"
    results[task.id] = {
        "error": error,
        "attempt": task.attempt,
        "max_attempts": task.max_attempts,
        "retry_scheduled": True,
        "retry_delay_seconds": delay_seconds,
        "next_attempt_at": task.next_attempt_at,
    }


def mark_task_failed(
    task: TaskEvent,
    results: dict[str, dict[str, Any]],
    error: str,
) -> None:
    task.state = "failed"
    task.status_reason = error
    task.next_attempt_at = None
    task.finished_at = now()
    results[task.id] = {
        "error": error,
        "attempt": task.attempt,
        "max_attempts": task.max_attempts,
    }


def mark_task_cancelled(
    task: TaskEvent,
    results: dict[str, dict[str, Any]],
    reason: str,
) -> None:
    task.state = "cancelled"
    task.next_attempt_at = None
    task.finished_at = now()
    results[task.id] = {"cancel_reason": reason}


def mark_task_skipped(
    task: TaskEvent,
    results: dict[str, dict[str, Any]],
    reason: str,
) -> None:
    task.state = "skipped"
    task.status_reason = reason
    task.next_attempt_at = None
    task.finished_at = now()
    results[task.id] = {"skip_reason": reason}


def reset_task_for_retry(task: TaskEvent, results: dict[str, dict[str, Any]]) -> None:
    task.state = "queued"
    task.status_reason = None
    task.next_attempt_at = None
    task.started_at = None
    task.finished_at = None
    task.attempt = 0
    results.pop(task.id, None)


def unblock_released_tasks(
    tasks: dict[str, TaskEvent],
    results: dict[str, dict[str, Any]],
    *,
    dependency_task_id: str,
) -> list[TaskEvent]:
    released: list[TaskEvent] = []
    while True:
        snapshot = snapshot_tasks(tasks)
        unblocked = [
            item
            for item in snapshot.values()
            if item.state == "blocked" and dependency_blocked_reason(item, snapshot) is None
        ]
        if not unblocked:
            break
        for dependent in unblocked:
            dependent.state = "queued"
            dependent.status_reason = None
            dependent.next_attempt_at = None
            dependent.finished_at = None
            results.pop(dependent.id, None)
            released.append(dependent)
    return released


def blocked_tasks_to_mark(tasks: dict[str, TaskEvent], results: dict[str, dict[str, Any]]) -> tuple[list[TaskEvent], list[tuple[TaskEvent, str]]]:
    blocked: list[TaskEvent] = []
    waiting: list[tuple[TaskEvent, str]] = []
    snapshot = snapshot_tasks(tasks)
    for task in snapshot.values():
        blocked_reason = dependency_blocked_reason(task, snapshot)
        if task.state in {"queued", "waiting"} and blocked_reason:
            mark_task_blocked(task, results, blocked_reason)
            blocked.append(task)
            continue
        reason = waiting_reason(task, snapshot)
        if task.state == "queued" and reason:
            mark_task_waiting(task, results, reason)
            waiting.append((task, reason))
    return blocked, waiting
