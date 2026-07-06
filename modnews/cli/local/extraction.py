from __future__ import annotations

from typing import Any

from modnews.service.extraction.repair_runtime_facade import RepairRuntimeFacade
from modnews.service.extraction.registry import registry_from_project
from modnews.service.extraction.web_source_runtime import WebSourceRuntimeFacade
from modnews.repository.web_jobs import WebJobStore


class ExtractionLocalMixin:
    def extractors_list(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in registry_from_project(self.project_root).list()]

    def extractor_show(self, source_id: str) -> dict[str, Any]:
        registry = registry_from_project(self.project_root)
        record = registry.get(source_id).to_dict()
        web_jobs = WebJobStore(self.project_root).list()
        repair_tasks = RepairManager(self.project_root, registry).list_tasks()
        config = self.config_show()
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

    def extractor_set_enabled(self, source_id: str, enabled: bool) -> dict[str, Any]:
        return registry_from_project(self.project_root).set_enabled(source_id, enabled).to_dict()

    def extractor_delete(self, source_id: str) -> None:
        registry_from_project(self.project_root).delete(source_id)

    def web_jobs(self) -> list[dict[str, Any]]:
        return WebJobStore(self.project_root).list()

    def web_job(self, job_id: str, include_events: bool = False) -> dict[str, Any]:
        return WebJobStore(self.project_root).get_dict(job_id, include_events=include_events)

    def web_job_events(self, job_id: str) -> list[dict[str, Any]]:
        return WebJobStore(self.project_root).events(job_id)

    def web_source_run(self, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._web_source_runtime().run_source(source_id, payload)

    def repair_tasks(self) -> list[dict[str, Any]]:
        return self._repair_runtime().list_tasks()

    def repair_task(self, task_id: str) -> dict[str, Any]:
        return self._repair_runtime().get_task(task_id)

    def repair_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._repair_runtime().create_task(payload)

    def repair_retry(self, task_id: str) -> dict[str, Any]:
        return self._repair_runtime().retry_task(task_id)

    def repair_promote(self, task_id: str) -> dict[str, Any]:
        return self._repair_runtime().promote_task(task_id)

    def repair_delete(self, task_id: str) -> dict[str, Any]:
        return self._repair_runtime().delete_task(task_id)

    def _repair_runtime(self) -> RepairRuntimeFacade:
        return RepairRuntimeFacade(
            project_root=self.project_root,
            queue=self.container.event_queue,
            queue_show=self.queue_show,
        )

    def _web_source_runtime(self) -> WebSourceRuntimeFacade:
        return WebSourceRuntimeFacade(
            project_root=self.project_root,
            queue=self.container.event_queue,
            queue_show=self.queue_show,
        )
