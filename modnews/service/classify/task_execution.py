from __future__ import annotations

from modnews.core.task import TaskEvent

from .runner import ClassifyStepRunner
from .steps import ClassifyStepDefinition
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
