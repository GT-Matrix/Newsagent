from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.service.pipeline.step import PipelineStepDescriptor
from modnews.service.report.planner import plan_report_tasks
from modnews.service.task_entrypoints import run_planned_tasks


def run_report_tasks(
    *,
    project_root: Path,
    queue: Any,
    queue_show: Any,
    input_path: str,
    run_id: str | None = None,
    output_dir: str | None = None,
    date: str | None = None,
    config: str | None = None,
    pipeline_descriptors: list[PipelineStepDescriptor] | None = None,
) -> dict[str, Any]:
    tasks = plan_report_tasks(
        project_root=project_root,
        input_path=input_path,
        run_id=run_id,
        output_dir=output_dir,
        date=date,
        config=config,
    )
    task_run_id = tasks[0].pipeline_run_id if tasks else (run_id or "report")
    result = run_planned_tasks(
        project_root=project_root,
        queue=queue,
        queue_show=queue_show,
        run_id=str(task_run_id),
        tasks=tasks,
        create_payload={
            "source": "manual_report_entrypoint",
            "input_path": input_path,
            "output_dir": output_dir,
            "date": date,
            "config": config,
        },
        pipeline_descriptors=pipeline_descriptors,
    )
    queue_task = result["tasks"][0] if result["tasks"] else {}
    task_result = queue_task.get("result", {}) if isinstance(queue_task.get("result"), dict) else {}
    stats = task_result.get("stats", {}) if isinstance(task_result.get("stats"), dict) else {}
    return {
        **result,
        "task": queue_task,
        "event_count": stats.get("event_count", 0),
        "selected_count": stats.get("selected_count", 0),
        "events_with_sources": stats.get("events_with_sources", 0),
        "output_dir": task_result.get("report_output_dir"),
    }
