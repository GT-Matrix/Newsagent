from __future__ import annotations

from typing import Any

from modnews.service.report.entrypoints import run_report_tasks


class ReportLocalMixin:
    def report_generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return run_report_tasks(
            project_root=self.project_root,
            queue=self.container.event_queue,
            queue_show=self.queue_show,
            input_path=str(payload["input"]),
            run_id=payload.get("run_id"),
            output_dir=str(payload["output_dir"]) if payload.get("output_dir") else None,
            date=payload.get("date"),
            config=str(payload["config"]) if payload.get("config") else None,
            pipeline_descriptors=self.container.pipeline_manager.describe_steps(),
        )
