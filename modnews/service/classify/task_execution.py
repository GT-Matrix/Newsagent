from __future__ import annotations

from modnews.core.task import TaskEvent

from .runner import ClassifyStepRunner
from .steps import ClassifyStepDefinition
from .steps import build_extraction_task_steps, build_merge_task_steps
from .task_checkpoint import write_classify_task_checkpoint
from .task_runtime import prepare_clustered_task_runtime


def execute_classify_task(
    task: TaskEvent,
    *,
    step_id: str,
    steps: list[ClassifyStepDefinition],
    auto_publish: bool = False,
) -> dict[str, object]:
    task_runtime = prepare_clustered_task_runtime(task)
    state = ClassifyStepRunner(steps).run(task_runtime.state, task_runtime.runtime)
    return write_classify_task_checkpoint(
        task_runtime.project_root,
        task_runtime.run_id,
        task,
        step_id,
        task_runtime.input_path,
        state,
        task_runtime.runtime,
        auto_publish=auto_publish,
    )


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
