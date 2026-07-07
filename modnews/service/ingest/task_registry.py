from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modnews.core.task import TaskEvent


@dataclass(frozen=True, slots=True)
class RegisteredIngestTask:
    task_type: str
    step_id_prefix: str
    task_id_prefix: str
    concurrency_key_prefix: str
    max_concurrency: int


REGISTERED_INGEST_TASKS: tuple[RegisteredIngestTask, ...] = (
    RegisteredIngestTask(
        task_type="ingest.run_step",
        step_id_prefix="ingest",
        task_id_prefix="ingest",
        concurrency_key_prefix="ingest",
        max_concurrency=1,
    ),
)

REGISTERED_INGEST_TASK_BY_TYPE: dict[str, RegisteredIngestTask] = {
    spec.task_type: spec
    for spec in REGISTERED_INGEST_TASKS
}


def get_registered_ingest_task(task_type: str) -> RegisteredIngestTask:
    return REGISTERED_INGEST_TASK_BY_TYPE[task_type]


def build_registered_ingest_step_task(
    spec: RegisteredIngestTask,
    *,
    project_root: Path,
    run_id: str,
    step_name: str,
    config_path: object = None,
    options: dict[str, Any] | None = None,
) -> TaskEvent:
    task_options = options if isinstance(options, dict) else {}
    return TaskEvent(
        id=f"{spec.task_id_prefix}-{run_id}-{step_name}",
        type=spec.task_type,
        pipeline_run_id=run_id,
        step_id=f"{spec.step_id_prefix}/{step_name}",
        payload={
            "project_root": str(project_root),
            "run_id": run_id,
            "config": config_path,
            "step_id": step_name,
            "options": task_options,
        },
        concurrency_key=f"{spec.concurrency_key_prefix}:{step_name}",
        max_concurrency=spec.max_concurrency,
    )
