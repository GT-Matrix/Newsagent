from __future__ import annotations

from modnews.core.task import TaskEvent

from .task_registry import REGISTERED_CLASSIFY_TASKS, get_registered_classify_task
from .runner import ClassifyStepRunner
from .task_checkpoint import write_classify_task_checkpoint
from .task_runtime import prepare_clustered_task_runtime


def execute_classify_task(
    task: TaskEvent,
) -> dict[str, object]:
    spec = get_registered_classify_task(task.type)
    task_runtime = prepare_clustered_task_runtime(task)
    run_result = ClassifyStepRunner(spec.build_steps()).run(task_runtime.state, task_runtime.runtime)
    return write_classify_task_checkpoint(
        task_runtime.project_root,
        task_runtime.run_id,
        task,
        spec,
        task_runtime.input_path,
        run_result,
        task_runtime.runtime.config,
    )


def run_clustered_event_extraction_task(task: TaskEvent) -> dict[str, object]:
    return execute_classify_task(task)


def run_clustered_event_merge_task(task: TaskEvent) -> dict[str, object]:
    return execute_classify_task(task)


REGISTERED_CLASSIFY_TASK_EXECUTORS: dict[str, object] = {
    spec.task_type: execute_classify_task
    for spec in REGISTERED_CLASSIFY_TASKS
}
