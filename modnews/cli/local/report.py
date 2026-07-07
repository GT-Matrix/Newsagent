from __future__ import annotations

from typing import Any

from modnews.service.report.runtime_facade import ReportRuntimeFacade


class ReportLocalMixin:
    def report_generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._report_runtime().run(payload)

    def _report_runtime(self) -> ReportRuntimeFacade:
        return ReportRuntimeFacade(
            project_root=self.project_root,
            queue=self.container.event_queue,
            queue_show=self.queue_show,
            pipeline_descriptors=self.container.pipeline_manager.describe_steps(),
        )
