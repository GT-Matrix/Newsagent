from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews_pipeline.web_extraction.job_store import WebJobStore


class WebJobRepository:
    def __init__(self, project_root: Path) -> None:
        self.store = WebJobStore(project_root)

    def list(self) -> list[dict[str, Any]]:
        return self.store.list()

    def get(self, job_id: str, include_events: bool = False) -> dict[str, Any]:
        return self.store.get_dict(job_id, include_events=include_events)

    def events(self, job_id: str) -> list[dict[str, Any]]:
        return self.store.events(job_id)
