from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from datetime import datetime


_QUEUE_STATE_CACHE: dict[str, dict[str, Any]] = {}
_QUEUE_STATE_LOCK = threading.RLock()


class QueueStateRepository:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def load(self) -> dict[str, Any]:
        with _QUEUE_STATE_LOCK:
            cached = _QUEUE_STATE_CACHE.get(str(self.project_root))
            if isinstance(cached, dict):
                cached = {
                    "version": int(cached.get("version") or 1),
                    "saved_at": cached.get("saved_at"),
                    "tasks": list(cached.get("tasks") or []),
                    "results": dict(cached.get("results") or {}),
                }
        if not isinstance(cached, dict):
            return {"version": 1, "saved_at": None, "tasks": [], "results": {}}
        return cached

    def save(self, payload: dict[str, Any]) -> None:
        with _QUEUE_STATE_LOCK:
            key = str(self.project_root)
            current = _QUEUE_STATE_CACHE.get(key)
            if not isinstance(current, dict) or payload.get("op") == "replace":
                _QUEUE_STATE_CACHE[key] = _snapshot_payload(payload)
                return

            task_rows = {
                str(task.get("id")): dict(task)
                for task in current.get("tasks", [])
                if isinstance(task, dict) and task.get("id")
            }
            results = dict(current.get("results") or {})
            op = str(payload.get("op") or "")
            if op == "upsert":
                task = payload.get("task")
                if isinstance(task, dict) and task.get("id"):
                    task_id = str(task["id"])
                    task_rows[task_id] = dict(task)
                    result = payload.get("result")
                    if isinstance(result, dict):
                        results[task_id] = dict(result)
            elif op == "upsert_many":
                for task in payload.get("tasks") or []:
                    if isinstance(task, dict) and task.get("id"):
                        task_rows[str(task["id"])] = dict(task)
                raw_results = payload.get("results")
                if isinstance(raw_results, dict):
                    for task_id, result in raw_results.items():
                        if isinstance(result, dict):
                            results[str(task_id)] = dict(result)
            else:
                _QUEUE_STATE_CACHE[key] = _snapshot_payload(payload)
                return

            _QUEUE_STATE_CACHE[key] = {
                "version": int(current.get("version") or 1),
                "saved_at": payload.get("saved_at") or datetime.now().astimezone().isoformat(timespec="seconds"),
                "tasks": list(task_rows.values()),
                "results": results,
            }


def _snapshot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": int(payload.get("version") or 1),
        "saved_at": payload.get("saved_at") or datetime.now().astimezone().isoformat(timespec="seconds"),
        "tasks": list(payload.get("tasks") or []),
        "results": dict(payload.get("results") or {}),
    }
