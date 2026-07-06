from __future__ import annotations

from typing import Any

from modnews.service.report.planner import plan_report_tasks


class ReportLocalMixin:
    def report_generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        tasks = plan_report_tasks(
            project_root=self.project_root,
            input_path=str(payload["input"]),
            run_id=payload.get("run_id"),
            output_dir=str(payload["output_dir"]) if payload.get("output_dir") else None,
            date=payload.get("date"),
            config=str(payload["config"]) if payload.get("config") else None,
        )
        for task in tasks:
            self.container.event_queue.register(task)
        self.container.event_queue.drain_ready()
        queue_task = self.queue_show(tasks[0].id)
        result = queue_task.get("result", {}) if isinstance(queue_task.get("result"), dict) else {}
        stats = result.get("stats", {}) if isinstance(result.get("stats"), dict) else {}
        return {
            "ok": queue_task.get("state") == "succeeded",
            "task": queue_task,
            "event_count": stats.get("event_count", 0),
            "selected_count": stats.get("selected_count", 0),
            "events_with_sources": stats.get("events_with_sources", 0),
            "output_dir": result.get("report_output_dir"),
        }
