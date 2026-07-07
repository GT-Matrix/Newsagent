from __future__ import annotations

from modnews.core.task import TaskEvent
from modnews.service.extraction.repair_node_runtime import (
    run_codex_repair_exec_task,
    run_codex_repair_node,
)
from modnews.service.extraction.task_registry import REGISTERED_EXTRACTION_TASKS


def run_codex_repair_task(task: TaskEvent) -> dict[str, object]:
    return run_codex_repair_node(task)


REGISTERED_REPAIR_TASK_EXECUTORS: dict[str, object] = {
    "extractor.repair.codex": run_codex_repair_task,
    "extractor.repair.codex.exec": run_codex_repair_exec_task,
}

assert {spec.task_type for spec in REGISTERED_EXTRACTION_TASKS if spec.task_type == "extractor.repair.codex"} <= set(REGISTERED_REPAIR_TASK_EXECUTORS)
