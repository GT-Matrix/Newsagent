from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.paths import runtime_paths
from modnews.core.progress import ProgressEvent
from modnews.core.task import TaskEvent
from modnews.repository.event_jsonl import append_event, read_events


class TaskLogRepository:
    def __init__(self, project_root: Path) -> None:
        self.root = runtime_paths(project_root).process_dir / "task_logs"

    def append(self, task: TaskEvent, event_type: str, **payload: Any) -> dict[str, Any]:
        return append_event(
            self._path(task.id),
            event_type,
            task_id=task.id,
            task_type=task.type,
            pipeline_run_id=task.pipeline_run_id,
            step_id=task.step_id,
            state=task.state,
            attempt=task.attempt,
            **payload,
        )

    def list(self, task_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        return read_events(self._path(task_id), limit=limit)

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

    def _path(self, task_id: str) -> Path:
        safe = task_id.replace("/", "_")
        return self.root / f"{safe}.jsonl"
