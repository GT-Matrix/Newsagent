from __future__ import annotations

from pathlib import Path

from modnews.core.task import TaskBlocked, TaskEvent
from modnews.service.extraction.registry import registry_from_project
from modnews.service.extraction.repair import RepairManager


def run_codex_repair_task(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    repair_task_id = str(task.payload["repair_task_id"])
    manager = RepairManager(project_root, registry_from_project(project_root))
    manager.run_task(repair_task_id)
    repair_task = manager.get_task(repair_task_id)
    status = str(repair_task.get("status") or "")
    if status == "blocked":
        raise TaskBlocked(
            str(repair_task.get("error") or "repair task blocked"),
            details={"repair_task": repair_task},
        )
    if status != "succeeded":
        raise RuntimeError(str(repair_task.get("error") or f"repair task ended as {status}"))
    return {"repair_task": repair_task}

