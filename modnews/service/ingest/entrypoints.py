from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.service.ingest.planner import plan_ingest_tasks
from modnews.service.task_entrypoints import run_planned_tasks


def run_ingest_step_tasks(
    *,
    project_root: Path,
    queue: Any,
    queue_show: Any,
    step_id: str,
    run_id: str | None = None,
    config_path: object = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_run_id = run_id or f"ingest-{step_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    tasks = plan_ingest_tasks(
        project_root=project_root,
        step_id=step_id,
        run_id=task_run_id,
        config_path=config_path,
        options=options,
    )
    return run_planned_tasks(
        project_root=project_root,
        queue=queue,
        queue_show=queue_show,
        run_id=task_run_id,
        tasks=tasks,
        create_payload={"source": "manual_ingest_entrypoint", "step_id": step_id, "options": options or {}},
    )
