from __future__ import annotations

from modnews.core.task import TaskEvent
from modnews.service.report import generate_report
from modnews.service.report.task_result import build_report_task_stats, persist_report_task_result
from modnews.service.report.task_runtime import build_report_task_runtime, resolve_report_input


def run_report_generate_task(task: TaskEvent) -> dict[str, object]:
    runtime = build_report_task_runtime(task)
    events = generate_report(
        runtime.input_path,
        runtime.output_dir,
        report_date=task.payload.get("date"),
        config_path=runtime.config_path,
    )
    return persist_report_task_result(
        project_root=runtime.project_root,
        run_id=runtime.run_id,
        task_id=task.id,
        input_path=runtime.input_path,
        output_dir=runtime.output_dir,
        stats=build_report_task_stats(events),
    )


_resolve_report_input = resolve_report_input
