from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.core.progress import emit
from modnews.service.extraction.web_contract import WebJob, WebSource

_JOBS_BY_ROOT: dict[str, dict[str, dict[str, Any]]] = {}
_EVENTS_BY_ROOT: dict[str, dict[str, list[dict[str, Any]]]] = {}
_ROOT_LOCK = threading.Lock()


class WebJobStore:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.root = self.project_root / ".agent_work" / "web_jobs"
        self._root_key = str(self.project_root)
        self._lock = threading.Lock()
        with _ROOT_LOCK:
            _JOBS_BY_ROOT.setdefault(self._root_key, {})
            _EVENTS_BY_ROOT.setdefault(self._root_key, {})

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
        rows = [dict(row) for row in _JOBS_BY_ROOT.get(self._root_key, {}).values()]
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
        raw = _JOBS_BY_ROOT.get(self._root_key, {}).get(job_id)
        if raw is None:
            raise KeyError(job_id)
        raw = dict(raw)
        if include_events:
            raw["events"] = self.events(job_id)
        return raw

    def save(self, job: WebJob) -> None:
        job.updated_at = _now()
        with self._lock:
            _JOBS_BY_ROOT.setdefault(self._root_key, {})[job.id] = job.to_dict()

    def append(self, job_id: str, event_type: str, **payload: Any) -> dict[str, Any]:
        job = self.get(job_id)
        event = {"ts": _now(), "type": event_type, "job_id": job.id, **payload}
        with self._lock:
            _EVENTS_BY_ROOT.setdefault(self._root_key, {}).setdefault(job.id, []).append(event)
        emit(
            "web_job_event",
            web_job_id=job.id,
            web_source_id=job.source_id,
            web_event_type=event_type,
            **payload,
        )
        return event

    def events(self, job_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        self.get(job_id)
        rows = list(_EVENTS_BY_ROOT.get(self._root_key, {}).get(job_id, []))
        if limit is not None:
            return rows[-limit:]
        return rows

    def job_dir(self, job_id: str, source_id: str) -> Path:
        return self.root / source_id / job_id


class WebJobRepository:
    def __init__(self, project_root: Path) -> None:
        self.store = WebJobStore(project_root)

    def list(self) -> list[dict[str, Any]]:
        return self.store.list()

    def get(self, job_id: str, include_events: bool = False) -> dict[str, Any]:
        return self.store.get_dict(job_id, include_events=include_events)

    def events(self, job_id: str) -> list[dict[str, Any]]:
        return self.store.events(job_id)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
