from __future__ import annotations

from typing import Any

from modnews.service.extraction.query_facade import ExtractionQueryFacade
from modnews.service.extraction.repair_runtime_facade import RepairRuntimeFacade
from modnews.service.extraction.registry import registry_from_project
from modnews.service.extraction.web_source_runtime import WebSourceRuntimeFacade


class ExtractionLocalMixin:
    def extractors_list(self) -> list[dict[str, Any]]:
        return self._extraction_queries().list_extractors()

    def extractor_show(self, source_id: str) -> dict[str, Any]:
        return self._extraction_queries().show_extractor(source_id, config=self.config_show())

    def extractor_set_enabled(self, source_id: str, enabled: bool) -> dict[str, Any]:
        return self._extraction_queries().set_extractor_enabled(source_id, enabled)

    def extractor_delete(self, source_id: str) -> None:
        self._extraction_queries().delete_extractor(source_id)

    def web_jobs(self) -> list[dict[str, Any]]:
        return self._extraction_queries().list_web_jobs()

    def web_job(self, job_id: str, include_events: bool = False) -> dict[str, Any]:
        return self._extraction_queries().show_web_job(job_id, include_events=include_events)

    def web_job_events(self, job_id: str) -> list[dict[str, Any]]:
        return self._extraction_queries().list_web_job_events(job_id)

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
            pipeline_descriptors=self.container.pipeline_manager.describe_steps(),
        )

    def _extraction_queries(self) -> ExtractionQueryFacade:
        return ExtractionQueryFacade(
            project_root=self.project_root,
            repair_runtime=self._repair_runtime(),
        )
