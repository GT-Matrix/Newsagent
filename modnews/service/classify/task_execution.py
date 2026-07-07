from __future__ import annotations

from modnews.core.task import TaskEvent

from .extraction_node_runtime import run_clustered_event_extraction_node
from .merge_node_runtime import run_clustered_event_merge_node
from .task_registry import REGISTERED_CLASSIFY_TASKS


def run_clustered_event_extraction_task(task: TaskEvent) -> dict[str, object]:
    return run_clustered_event_extraction_node(task)


def run_clustered_event_merge_task(task: TaskEvent) -> dict[str, object]:
    return run_clustered_event_merge_node(task)


REGISTERED_CLASSIFY_TASK_EXECUTORS: dict[str, object] = {
    "classify.clustered_event_extraction": run_clustered_event_extraction_task,
    "classify.clustered_event_merge": run_clustered_event_merge_task,
}
