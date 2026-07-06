from __future__ import annotations

from datetime import datetime
from pathlib import Path

from modnews.core.task import TaskEvent


def plan_report_tasks(
    *,
    project_root: Path,
    input_path: str,
    run_id: str | None = None,
    output_dir: str | None = None,
    date: str | None = None,
    config: str | None = None,
) -> list[TaskEvent]:
    task_run_id = run_id or f"report-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    return [
        TaskEvent(
            id=f"report-{task_run_id}-generate",
            type="report.generate",
            pipeline_run_id=task_run_id,
            step_id="report/generate",
            payload={
                "project_root": str(project_root),
                "run_id": task_run_id,
                "config": config,
                "input_path": input_path,
                "output_dir": output_dir,
                "date": date,
            },
            concurrency_key="report",
            max_concurrency=1,
        )
    ]
