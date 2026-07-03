from __future__ import annotations

from datetime import datetime
from typing import Any

from modnews.core.task import TaskEvent
from modnews_pipeline.extractors.registry import registry_from_project
from modnews_pipeline.extractors.repair import RepairManager
from modnews_pipeline.web_extraction.job_store import WebJobStore


class ExtractionLocalMixin:
    def extractors_list(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in registry_from_project(self.project_root).list()]

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
            auto_start=bool(payload.get("auto_start", True)),
        )
        return {"ok": True, "item": task.to_dict()}

    def repair_retry(self, task_id: str) -> dict[str, Any]:
        task = RepairManager(self.project_root, registry_from_project(self.project_root)).retry_task(task_id)
        return {"ok": True, "item": task.to_dict()}

    def repair_promote(self, task_id: str) -> dict[str, Any]:
        task = RepairManager(self.project_root, registry_from_project(self.project_root)).promote_task(task_id)
        return {"ok": True, "item": task.to_dict()}

    def repair_delete(self, task_id: str) -> dict[str, Any]:
        RepairManager(self.project_root, registry_from_project(self.project_root)).delete_task(task_id)
        return {"ok": True}
