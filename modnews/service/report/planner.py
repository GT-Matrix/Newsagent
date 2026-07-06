from __future__ import annotations

from pathlib import Path

from modnews.core.task import TaskEvent

from .task_registry import (
    build_registered_report_task,
    get_registered_report_task,
    resolve_report_run_id,
)


def plan_report_tasks(
    *,
    project_root: Path,
    input_path: str,
    run_id: str | None = None,
    output_dir: str | None = None,
    date: str | None = None,
    config: str | None = None,
) -> list[TaskEvent]:
    task_run_id = resolve_report_run_id(run_id)
    return [
        build_registered_report_task(
            get_registered_report_task("report.generate"),
            project_root=project_root,
            run_id=task_run_id,
            input_path=input_path,
            output_dir=output_dir,
            date=date,
            config=config,
        )
    ]
