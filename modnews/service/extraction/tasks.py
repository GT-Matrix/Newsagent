from __future__ import annotations

from modnews.core.task import TaskEvent
from modnews.service.extraction.task_registry import REGISTERED_EXTRACTION_TASKS
from modnews.service.extraction.web_source_node_runtime import (
    run_web_source_node,
    run_web_source_scrape_task,
)


def run_web_source_task(task: TaskEvent) -> dict[str, object]:
    return run_web_source_node(task)


REGISTERED_EXTRACTION_TASK_EXECUTORS: dict[str, object] = {
    "web_source.run": run_web_source_task,
    "web_source.scrape": run_web_source_scrape_task,
}

assert {spec.task_type for spec in REGISTERED_EXTRACTION_TASKS if spec.task_type == "web_source.run"} <= set(REGISTERED_EXTRACTION_TASK_EXECUTORS)
