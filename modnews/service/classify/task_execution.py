from __future__ import annotations

from modnews.core.task import TaskEvent

from .extraction_node_runtime import run_clustered_event_extraction_node
from .merge_node_runtime import run_clustered_event_merge_node
from .task_registry import REGISTERED_CLASSIFY_TASKS, get_registered_classify_task
from .runner import ClassifyStepRunner
from .step_observer import EmittingClassifyStepObserver
from .task_checkpoint import write_classify_task_checkpoint
from .task_runtime import prepare_clustered_task_runtime


def execute_classify_task(
    task: TaskEvent,
) -> dict[str, object]:
    spec = get_registered_classify_task(task.type)
    task_runtime = prepare_clustered_task_runtime(task)
    run_result = ClassifyStepRunner(
        spec.build_steps(),
        observer=EmittingClassifyStepObserver(),
    ).run(task_runtime.state, task_runtime.runtime)
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
    return run_clustered_event_extraction_node(task)


def run_clustered_event_merge_task(task: TaskEvent) -> dict[str, object]:
    return run_clustered_event_merge_node(task)


REGISTERED_CLASSIFY_TASK_EXECUTORS: dict[str, object] = {
    "classify.clustered_event_extraction": run_clustered_event_extraction_task,
    "classify.clustered_event_merge": run_clustered_event_merge_task,
}
