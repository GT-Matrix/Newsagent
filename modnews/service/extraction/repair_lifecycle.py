from __future__ import annotations

from pathlib import Path

from modnews.service.extraction.registry import ExtractorRegistry
from modnews.service.extraction.repair_promote import promote_repair_task
from modnews.service.extraction.repair_runtime import run_repair_task
from modnews.service.extraction.repair_store import RepairTask, read_json


def run_and_promote_repair_task(
    *,
    project_root: Path,
    registry: ExtractorRegistry,
    task: RepairTask,
) -> RepairTask:
    task = run_repair_task(task)
    if task.status != "succeeded":
        return task
    result = read_json(task.result_path, {})
    if result.get("status") not in {"fixed", "needs_review"}:
        return task
    try:
        return promote_repair_task(project_root, registry, task)
    except Exception:
        return task
