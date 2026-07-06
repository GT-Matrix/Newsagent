from __future__ import annotations

from pathlib import Path

from modnews.core.progress import emit
from modnews.core.task import TaskEvent
from modnews.service.extraction.registry import registry_from_project
from modnews.service.extraction.repair import RepairManager
from modnews.service.extraction.repair_task_result import build_repair_task_result
from modnews.service.extraction.task_registry import REGISTERED_EXTRACTION_TASKS


def run_codex_repair_task(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    repair_task_id = str(task.payload["repair_task_id"])
    manager = RepairManager(project_root, registry_from_project(project_root))
    manager.run_task(repair_task_id)
    repair_task = manager.get_task(repair_task_id)
    log_summary = manager.store.codex_log_summary(repair_task_id)
    emit(
        "codex_repair_log",
        repair_task_id=repair_task_id,
        source_id=repair_task.get("source_id"),
        status=repair_task.get("status"),
        **log_summary,
    )
    return build_repair_task_result(repair_task, log_summary)


REGISTERED_REPAIR_TASK_EXECUTORS: dict[str, object] = {
    "extractor.repair.codex": run_codex_repair_task,
}

assert {spec.task_type for spec in REGISTERED_EXTRACTION_TASKS if spec.task_type == "extractor.repair.codex"} <= set(REGISTERED_REPAIR_TASK_EXECUTORS)
