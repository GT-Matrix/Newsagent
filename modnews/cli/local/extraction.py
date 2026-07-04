from __future__ import annotations

from datetime import datetime
from typing import Any

from modnews.core.task import TaskEvent
from modnews.service.extraction.repair import RepairManager
from modnews.service.extraction.registry import registry_from_project
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
        task_id = str(payload.get("task_id") or f"web-source-{source_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
        task = TaskEvent(
            id=task_id,
            type="web_source.run",
            step_id="web_source",
            payload={
                "project_root": str(self.project_root),
                "source_id": source_id,
                "limit": payload.get("limit"),
                "scrape_date": payload.get("scrape_date"),
            },
            concurrency_key=f"web_source:{source_id}",
            max_concurrency=1,
        )
        self.container.event_queue.submit(task)
        result = self.queue_show(task_id)
        job = result.get("result", {}).get("job") if isinstance(result.get("result"), dict) else None
        return {"ok": result.get("state") == "succeeded", "task": result, "item": job}

    def repair_tasks(self) -> list[dict[str, Any]]:
        return RepairManager(self.project_root, registry_from_project(self.project_root)).list_tasks()

    def repair_task(self, task_id: str) -> dict[str, Any]:
        return RepairManager(self.project_root, registry_from_project(self.project_root)).get_task(task_id)

    def repair_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = RepairManager(self.project_root, registry_from_project(self.project_root)).create_task(
            str(payload["source_id"]),
            reason=str(payload.get("reason") or "manual repair request"),
            auto_start=False,
        )
        queue_task = None
        if bool(payload.get("auto_start", True)):
            queue_task = self._submit_repair_task(task.id, task.source_id)
        return {"ok": True, "item": task.to_dict(), "task": queue_task}

    def repair_retry(self, task_id: str) -> dict[str, Any]:
        task = RepairManager(self.project_root, registry_from_project(self.project_root)).retry_task(task_id)
        queue_task = self._submit_repair_task(task.id, task.source_id)
        return {"ok": True, "item": task.to_dict(), "task": queue_task}

    def repair_promote(self, task_id: str) -> dict[str, Any]:
        task = RepairManager(self.project_root, registry_from_project(self.project_root)).promote_task(task_id)
        return {"ok": True, "item": task.to_dict()}

    def repair_delete(self, task_id: str) -> dict[str, Any]:
        RepairManager(self.project_root, registry_from_project(self.project_root)).delete_task(task_id)
        return {"ok": True}

    def _submit_repair_task(self, repair_task_id: str, source_id: str) -> dict[str, Any]:
        task_id = f"repair-{repair_task_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        task = TaskEvent(
            id=task_id,
            type="extractor.repair.codex",
            step_id="extractor/repair",
            payload={
                "project_root": str(self.project_root),
                "repair_task_id": repair_task_id,
                "source_id": source_id,
            },
            concurrency_key=f"extractor.repair:{source_id}",
            max_concurrency=1,
        )
        self.container.event_queue.submit(task)
        return self.queue_show(task_id)
