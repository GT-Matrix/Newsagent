from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modnews.repository.web_jobs import WebJobStore
from modnews.service.extraction.registry import registry_from_project
from modnews.service.extraction.repair_runtime_facade import RepairRuntimeFacade


@dataclass(slots=True)
class ExtractionQueryFacade:
    project_root: Path
    repair_runtime: RepairRuntimeFacade

    def list_extractors(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in registry_from_project(self.project_root).list()]

    def show_extractor(self, source_id: str, *, config: dict[str, Any]) -> dict[str, Any]:
        registry = registry_from_project(self.project_root)
        record = registry.get(source_id).to_dict()
        web_jobs = WebJobStore(self.project_root).list()
        repair_tasks = self.repair_runtime.list_tasks()
        site_sources = config.get("sources", {}).get("site_lists", {})
        bound_sources = []
        if isinstance(site_sources, dict):
            for site_id, row in site_sources.items():
                if isinstance(row, dict) and (row.get("extractor_id") or site_id) == source_id:
                    bound_sources.append({"id": site_id, **row})
        return {
            "record": record,
            "bound_sources": bound_sources,
            "recent_jobs": [
                job for job in web_jobs
                if job.get("extractor_id") == source_id or job.get("source_id") == source_id
            ][:10],
            "repair_tasks": [
                task for task in repair_tasks
                if task.get("source_id") == source_id
            ][:10],
        }

    def set_extractor_enabled(self, source_id: str, enabled: bool) -> dict[str, Any]:
        return registry_from_project(self.project_root).set_enabled(source_id, enabled).to_dict()

    def delete_extractor(self, source_id: str) -> None:
        registry_from_project(self.project_root).delete(source_id)

    def list_web_jobs(self) -> list[dict[str, Any]]:
        return WebJobStore(self.project_root).list()

    def show_web_job(self, job_id: str, *, include_events: bool = False) -> dict[str, Any]:
        return WebJobStore(self.project_root).get_dict(job_id, include_events=include_events)

    def list_web_job_events(self, job_id: str) -> list[dict[str, Any]]:
        return WebJobStore(self.project_root).events(job_id)
