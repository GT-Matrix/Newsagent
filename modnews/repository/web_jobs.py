from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from modnews_pipeline.paths import runtime_paths
from modnews.repository.event_jsonl import append_event, read_events
from modnews.service.extraction.web_contract import WebJob, WebSource


class WebJobStore:
    def __init__(self, project_root: Path) -> None:
        self.root = runtime_paths(project_root).agent_work_dir / "web_jobs"
        self._lock = threading.Lock()

    def create(self, source: WebSource, max_attempts: int) -> WebJob:
        now = _now()
        job = WebJob(
            id=f"{source.id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            source_id=source.id,
            source_name=source.name,
            extractor_id=source.extractor_id,
            content_type=source.content_type,
            url=source.url,
            state="queued",
            created_at=now,
            updated_at=now,
            max_attempts=max_attempts,
        )
        self.save(job)
        self.append(job.id, "job_created", source_id=source.id, state=job.state)
        return job

    def list(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        rows = [_read_json(path, {}) for path in self.root.glob("*/*/job.json")]
        return sorted([row for row in rows if row], key=lambda item: str(item.get("updated_at", "")), reverse=True)

    def get(self, job_id: str) -> WebJob:
        raw = self.get_dict(job_id)
        return WebJob(
            id=str(raw["id"]),
            source_id=str(raw["source_id"]),
            source_name=str(raw.get("source_name") or raw["source_id"]),
            extractor_id=raw.get("extractor_id"),
            content_type=str(raw.get("content_type") or "news"),
            url=str(raw.get("url") or ""),
            state=str(raw["state"]),
            created_at=str(raw["created_at"]),
            updated_at=str(raw["updated_at"]),
            attempts=int(raw.get("attempts", 0)),
            max_attempts=int(raw.get("max_attempts", 3)),
            item_count=int(raw.get("item_count", 0)),
            error_type=raw.get("error_type"),
            error=raw.get("error"),
            repair_task_id=raw.get("repair_task_id"),
            output_path=raw.get("output_path"),
            raw_result_path=raw.get("raw_result_path"),
        )

    def get_dict(self, job_id: str, include_events: bool = False) -> dict[str, Any]:
        path = self._find_job_path(job_id)
        if not path:
            raise KeyError(job_id)
        raw = _read_json(path, {})
        if include_events:
            raw["events"] = self.events(job_id)
        return raw

    def save(self, job: WebJob) -> None:
        job.updated_at = _now()
        path = self.job_dir(job.id, job.source_id) / "job.json"
        with self._lock:
            _write_json(path, job.to_dict())

    def append(self, job_id: str, event_type: str, **payload: Any) -> dict[str, Any]:
        job = self.get(job_id)
        return append_event(self.job_dir(job.id, job.source_id) / "events.jsonl", event_type, job_id=job.id, **payload)

    def events(self, job_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        job = self.get(job_id)
        return read_events(self.job_dir(job.id, job.source_id) / "events.jsonl", limit=limit)

    def job_dir(self, job_id: str, source_id: str) -> Path:
        return self.root / source_id / job_id

    def _find_job_path(self, job_id: str) -> Path | None:
        matches = list(self.root.glob(f"*/{job_id}/job.json"))
        return matches[0] if matches else None


class WebJobRepository:
    def __init__(self, project_root: Path) -> None:
        self.store = WebJobStore(project_root)

    def list(self) -> list[dict[str, Any]]:
        return self.store.list()

    def get(self, job_id: str, include_events: bool = False) -> dict[str, Any]:
        return self.store.get_dict(job_id, include_events=include_events)

    def events(self, job_id: str) -> list[dict[str, Any]]:
        return self.store.events(job_id)


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
