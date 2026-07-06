from __future__ import annotations

from datetime import datetime
from pathlib import Path

from modnews.core.task import TaskEvent


def build_repair_task_event(
    *,
    project_root: Path,
    repair_task_id: str,
    source_id: str,
    run_id: str | None = None,
    task_id: str | None = None,
) -> TaskEvent:
    event_id = task_id or f"repair-{repair_task_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    return TaskEvent(
        id=event_id,
        type="extractor.repair.codex",
        pipeline_run_id=run_id,
        step_id="extractor/repair",
        payload={
            "project_root": str(project_root),
            "repair_task_id": repair_task_id,
            "source_id": source_id,
        },
        concurrency_key=f"extractor.repair:{source_id}",
        max_concurrency=1,
    )
