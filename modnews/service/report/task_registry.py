from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from modnews.core.task import TaskEvent


@dataclass(frozen=True, slots=True)
class RegisteredReportTask:
    task_type: str
    step_id: str
    task_id_suffix: str
    concurrency_key: str
    max_concurrency: int
    default_input_path: str | None = None
    default_output_dir: str | None = None


REGISTERED_REPORT_TASKS: tuple[RegisteredReportTask, ...] = (
    RegisteredReportTask(
        task_type="report.generate",
        step_id="report/generate",
        task_id_suffix="generate",
        concurrency_key="report",
        max_concurrency=1,
        default_input_path="__latest_classify_checkpoint__",
        default_output_dir="data/output",
    ),
)

REGISTERED_REPORT_TASK_BY_TYPE: dict[str, RegisteredReportTask] = {
    spec.task_type: spec
    for spec in REGISTERED_REPORT_TASKS
}


def get_registered_report_task(task_type: str) -> RegisteredReportTask:
    return REGISTERED_REPORT_TASK_BY_TYPE[task_type]


def resolve_report_run_id(run_id: str | None) -> str:
    return run_id or f"report-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def build_registered_report_task(
    spec: RegisteredReportTask,
    *,
    project_root: Path,
    run_id: str,
    input_path: str | None = None,
    output_dir: str | None = None,
    date: str | None = None,
    config: str | None = None,
    depends_on: list[str] | None = None,
) -> TaskEvent:
    return TaskEvent(
        id=f"report-{run_id}-{spec.task_id_suffix}",
        type=spec.task_type,
        pipeline_run_id=run_id,
        step_id=spec.step_id,
        payload={
            "project_root": str(project_root),
            "run_id": run_id,
            "config": config,
            "input_path": input_path if input_path is not None else spec.default_input_path,
            "output_dir": output_dir if output_dir is not None else spec.default_output_dir,
            "date": date,
        },
        depends_on=list(depends_on or []),
        concurrency_key=spec.concurrency_key,
        max_concurrency=spec.max_concurrency,
    )
