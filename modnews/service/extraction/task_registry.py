from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from modnews.core.task import TaskEvent


@dataclass(frozen=True, slots=True)
class RegisteredExtractionTask:
    task_type: str
    step_id_prefix: str
    task_id_prefix: str
    concurrency_key_prefix: str
    max_concurrency: int
    max_attempts: int | None = None


REGISTERED_EXTRACTION_TASKS: tuple[RegisteredExtractionTask, ...] = (
    RegisteredExtractionTask(
        task_type="web_source.run",
        step_id_prefix="ingest/site_lists",
        task_id_prefix="web-source",
        concurrency_key_prefix="web_source",
        max_concurrency=1,
        max_attempts=1,
    ),
    RegisteredExtractionTask(
        task_type="extractor.repair.codex",
        step_id_prefix="extractor/repair",
        task_id_prefix="repair",
        concurrency_key_prefix="extractor.repair",
        max_concurrency=1,
    ),
)

REGISTERED_EXTRACTION_TASK_BY_TYPE: dict[str, RegisteredExtractionTask] = {
    spec.task_type: spec
    for spec in REGISTERED_EXTRACTION_TASKS
}


def get_registered_extraction_task(task_type: str) -> RegisteredExtractionTask:
    return REGISTERED_EXTRACTION_TASK_BY_TYPE[task_type]


def build_registered_web_source_task(
    spec: RegisteredExtractionTask,
    *,
    project_root: Path,
    run_id: str,
    source_id: str,
    config_path: object = None,
    limit: int,
    max_concurrency: int | None = None,
) -> TaskEvent:
    return TaskEvent(
        id=f"{spec.task_id_prefix}-{run_id}-{source_id}",
        type=spec.task_type,
        pipeline_run_id=run_id,
        step_id=f"{spec.step_id_prefix}/{source_id}",
        payload={
            "project_root": str(project_root),
            "run_id": run_id,
            "config": config_path,
            "source_id": source_id,
            "limit": limit,
        },
        concurrency_key=spec.concurrency_key_prefix,
        max_concurrency=max(1, max_concurrency if max_concurrency is not None else spec.max_concurrency),
        max_attempts=spec.max_attempts,
    )


def build_registered_repair_task(
    spec: RegisteredExtractionTask,
    *,
    project_root: Path,
    repair_task_id: str,
    source_id: str,
    run_id: str | None = None,
    task_id: str | None = None,
) -> TaskEvent:
    return TaskEvent(
        id=task_id or f"{spec.task_id_prefix}-{repair_task_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        type=spec.task_type,
        pipeline_run_id=run_id,
        step_id=spec.step_id_prefix,
        payload={
            "project_root": str(project_root),
            "repair_task_id": repair_task_id,
            "source_id": source_id,
        },
        concurrency_key=f"{spec.concurrency_key_prefix}:{source_id}",
        max_concurrency=spec.max_concurrency,
        max_attempts=spec.max_attempts,
    )
