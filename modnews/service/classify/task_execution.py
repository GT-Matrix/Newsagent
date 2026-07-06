from __future__ import annotations

from modnews.core.models import EventRecord, NewsItem, StepResult
from modnews.core.task import TaskEvent
from modnews.core.config import ClassificationConfig
from modnews.core.context import PipelineContext

from .run_result import build_classify_step_result
from .task_registry import REGISTERED_CLASSIFY_TASKS, get_registered_classify_task
from .runtime_build import build_classify_runtime_for_context, build_classify_state_from_items
from .runner import ClassifyStepRunner
from .steps import build_full_classify_steps
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


def run_classification(
    ctx: PipelineContext,
    items: list[NewsItem],
    config: ClassificationConfig,
) -> tuple[list[NewsItem], list[EventRecord], StepResult]:
    if not config.enabled:
        return items, [], StepResult(step="classify", item_count=len(items), meta={"enabled": False})

    state = build_classify_state_from_items(
        items,
        resume_checkpoint_path=config.checkpoint_path,
    )
    runtime = build_classify_runtime_for_context(
        ctx,
        config,
    )
    run_result = ClassifyStepRunner(build_full_classify_steps()).run(state, runtime)
    state = run_result.state

    return state.items, state.event_records, build_classify_step_result(
        config=config,
        run_result=run_result,
        step="classify",
    )
