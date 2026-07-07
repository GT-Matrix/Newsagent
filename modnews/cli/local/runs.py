from __future__ import annotations

from typing import Any

from modnews.repository.runs import RunRepository
from modnews.service.pipeline.query_facade import PipelineQueryFacade
from modnews.service.pipeline.runtime_facade import PipelineRuntimeFacade


class RunsLocalMixin:
    def _pipeline_queries(self) -> PipelineQueryFacade:
        return PipelineQueryFacade(
            self.project_root,
            self.container.event_queue,
            self.container.pipeline_manager.describe_steps(),
        )

    def _pipeline_runtime(self) -> PipelineRuntimeFacade:
        return PipelineRuntimeFacade(
            self.project_root,
            self.container.event_queue,
            self.container.pipeline_manager,
        )

    def run_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._pipeline_runtime().start(payload)

    def run_list(self) -> list[dict[str, Any]]:
        queries = self._pipeline_queries()
        return [
            queries.run_list_item(record)
            for record in RunRepository(self.project_root).list()
        ]

    def run_status(self, run_id: str | None = None) -> dict[str, Any]:
        if run_id:
            return self._pipeline_queries().run_detail(run_id)
        return {"runs": self.run_list(), "state": self.state()}

    def run_resume(self, run_id: str) -> dict[str, Any]:
        return self._pipeline_runtime().resume(run_id)

    def run_cancel(self, run_id: str, reason: str = "cancelled by user") -> dict[str, Any]:
        return self._pipeline_runtime().cancel(run_id, reason)

    def _run_tasks(self, run_id: str) -> list[dict[str, Any]]:
        return self._pipeline_runtime().run_tasks(run_id)
