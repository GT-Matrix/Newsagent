from __future__ import annotations

from modnews.core.task import TaskEvent
from modnews.service.classify.runner import ClassifyStepRunner
from modnews.service.classify.steps import build_extraction_task_steps, build_merge_task_steps
from modnews.service.classify.task_checkpoint import write_classify_task_checkpoint
from modnews.service.classify.task_runtime import prepare_clustered_task_runtime


def run_clustered_event_extraction_task(task: TaskEvent) -> dict[str, object]:
    task_runtime = prepare_clustered_task_runtime(task)
    state = ClassifyStepRunner(build_extraction_task_steps()).run(task_runtime.state, task_runtime.runtime)
    return write_classify_task_checkpoint(
        task_runtime.project_root,
        task_runtime.run_id,
        task,
        "classify/clustered_event_extraction",
        task_runtime.input_path,
        state,
        task_runtime.runtime,
    )


def run_clustered_event_merge_task(task: TaskEvent) -> dict[str, object]:
    task_runtime = prepare_clustered_task_runtime(task)
    state = ClassifyStepRunner(build_merge_task_steps()).run(task_runtime.state, task_runtime.runtime)
    return write_classify_task_checkpoint(
        task_runtime.project_root,
        task_runtime.run_id,
        task,
        "classify/clustered_event_merge",
        task_runtime.input_path,
        state,
        task_runtime.runtime,
        auto_publish=True,
    )
