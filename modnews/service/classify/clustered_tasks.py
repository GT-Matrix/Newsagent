from __future__ import annotations

from modnews.core.task import TaskEvent
from modnews.service.classify.task_execution import execute_classify_task
from modnews.service.classify.steps import build_extraction_task_steps, build_merge_task_steps


def run_clustered_event_extraction_task(task: TaskEvent) -> dict[str, object]:
    return execute_classify_task(
        task,
        step_id="classify/clustered_event_extraction",
        steps=build_extraction_task_steps(),
    )


def run_clustered_event_merge_task(task: TaskEvent) -> dict[str, object]:
    return execute_classify_task(
        task,
        step_id="classify/clustered_event_merge",
        steps=build_merge_task_steps(),
        auto_publish=True,
    )
