from __future__ import annotations

from modnews.core.task import TaskEvent
from modnews.service.report.node_runtime import (
    run_report_generate_node,
    run_report_polish_task,
    run_report_trend_summary_task,
)
from modnews.service.report.task_registry import REGISTERED_REPORT_TASKS
from modnews.service.report.task_runtime import resolve_report_input


def run_report_generate_task(task: TaskEvent) -> dict[str, object]:
    return run_report_generate_node(task)


REGISTERED_REPORT_TASK_EXECUTORS: dict[str, object] = {
    "report.generate": run_report_generate_task,
    "report.polish_event": run_report_polish_task,
    "report.trend_summary": run_report_trend_summary_task,
}

assert {spec.task_type for spec in REGISTERED_REPORT_TASKS}.issubset(set(REGISTERED_REPORT_TASK_EXECUTORS))


_resolve_report_input = resolve_report_input
