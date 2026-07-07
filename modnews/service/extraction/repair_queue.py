from __future__ import annotations

from pathlib import Path

from modnews.core.task import TaskEvent
from modnews.service.extraction.task_registry import (
    build_registered_repair_task,
    get_registered_extraction_task,
)


def build_repair_task_event(
    *,
    project_root: Path,
    repair_task_id: str,
    source_id: str,
    run_id: str | None = None,
    task_id: str | None = None,
) -> TaskEvent:
    return build_registered_repair_task(
        get_registered_extraction_task("extractor.repair.codex"),
        project_root=project_root,
        repair_task_id=repair_task_id,
        source_id=source_id,
        run_id=run_id,
        task_id=task_id,
    )
