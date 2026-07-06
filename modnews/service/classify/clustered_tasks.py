from __future__ import annotations

from modnews.core.task import TaskEvent
from modnews.service.classify.steps import ClusteredEventExtractionStep, ClusteredEventMergeStep, StartCheckpointStep
from modnews.service.classify.task_checkpoint import write_classify_task_checkpoint
from modnews.service.classify.task_runtime import prepare_clustered_task_runtime


def run_clustered_event_extraction_task(task: TaskEvent) -> dict[str, object]:
    task_runtime = prepare_clustered_task_runtime(task)
    state = task_runtime.state
    runtime = task_runtime.runtime
    start_step = StartCheckpointStep()
    if start_step.should_run(state):
        state = start_step.run(state, runtime)
    step = ClusteredEventExtractionStep()
    if step.should_run(state):
        state = step.run(state, runtime)
        state.stage = step.output_stage
    return write_classify_task_checkpoint(
        task_runtime.project_root,
        task_runtime.run_id,
        task,
        "classify/clustered_event_extraction",
        task_runtime.input_path,
        state,
        runtime,
    )


def run_clustered_event_merge_task(task: TaskEvent) -> dict[str, object]:
    task_runtime = prepare_clustered_task_runtime(task)
    state = task_runtime.state
    runtime = task_runtime.runtime
    step = ClusteredEventMergeStep()
    if step.should_run(state):
        state = step.run(state, runtime)
        state.stage = step.output_stage
    return write_classify_task_checkpoint(
        task_runtime.project_root,
        task_runtime.run_id,
        task,
        "classify/clustered_event_merge",
        task_runtime.input_path,
        state,
        runtime,
        auto_publish=True,
    )
