from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.core.progress import ProgressEvent
from modnews.core.task import TaskEvent


_TASK_LOG_CACHE: dict[tuple[str, str], list[dict[str, Any]]] = {}


class TaskLogRepository:
    def __init__(self, project_root: Path) -> None:
        self.project_root = str(project_root.resolve())

    def append(self, task: TaskEvent, event_type: str, **payload: Any) -> dict[str, Any]:
        event = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "type": event_type,
            "task_id": task.id,
            "task_type": task.type,
            "pipeline_run_id": task.pipeline_run_id,
            "step_id": task.step_id,
            "state": task.state,
            "attempt": task.attempt,
            **payload,
        }
        _TASK_LOG_CACHE.setdefault(self._key(task.id), []).append(event)
        return event

    def list(self, task_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        rows = list(_TASK_LOG_CACHE.get(self._key(task_id), []))
        return rows[-limit:] if limit else rows

    def append_progress(self, task: TaskEvent, event: ProgressEvent) -> dict[str, Any]:
        payload = event.to_dict()
        payload.pop("id", None)
        event_type = str(payload.pop("type", event.type))
        ts = payload.pop("ts", None)
        if ts is not None:
            payload["progress_ts"] = ts
        for key in ("task", "task_id", "task_type", "pipeline_run_id", "step_id", "state", "attempt"):
            if key in payload:
                payload[f"progress_{key}"] = payload.pop(key)
        return self.append(task, f"progress.{event_type}", **payload)

    def _key(self, task_id: str) -> tuple[str, str]:
        return (self.project_root, task_id)
