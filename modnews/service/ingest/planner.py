from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.core.task import TaskEvent
from modnews.service.ingest.registry import default_ingest_registry


def plan_ingest_tasks(
    *,
    project_root: Path,
    step_id: str,
    run_id: str | None = None,
    config_path: object = None,
    options: dict[str, Any] | None = None,
) -> list[TaskEvent]:
    task_run_id = run_id or f"ingest-{step_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    task_options = options if isinstance(options, dict) else {}
    step_cls = default_ingest_registry().get(step_id)
    return step_cls.plan_tasks(
        project_root=project_root,
        run_id=task_run_id,
        config_path=config_path,
        options=task_options,
    )
