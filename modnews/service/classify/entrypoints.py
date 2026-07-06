from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.service.classify.planner import plan_clustered_classify_tasks
from modnews.service.task_entrypoints import run_planned_tasks


def run_classify_tasks(
    *,
    project_root: Path,
    queue: Any,
    queue_show: Any,
    run_id: str | None,
    input_path: str | None,
    config: str | None = None,
) -> dict[str, Any]:
    tasks = plan_clustered_classify_tasks(
        project_root=project_root,
        run_id=run_id,
        input_path=input_path,
        config=config,
    )
    task_run_id = tasks[0].pipeline_run_id if tasks else (run_id or "classify")
    return run_planned_tasks(
        project_root=project_root,
        queue=queue,
        queue_show=queue_show,
        run_id=str(task_run_id),
        tasks=tasks,
        create_payload={"source": "manual_classify_entrypoint", "input_path": input_path, "config": config},
    )
