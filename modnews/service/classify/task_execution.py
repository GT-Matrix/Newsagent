from __future__ import annotations

from modnews.core.models import EventRecord, NewsItem, StepResult
from modnews.core.task import TaskEvent
from modnews.core.config import ClassificationConfig
from modnews.core.context import PipelineContext

from .runtime_build import build_classify_runtime_for_context, build_classify_state_from_items
from .runner import ClassifyStepRunner
from .runner import ClassifyStep
from .steps import build_extraction_task_steps, build_full_classify_steps, build_merge_task_steps
from .task_checkpoint import write_classify_task_checkpoint
from .task_runtime import prepare_clustered_task_runtime


def execute_classify_task(
    task: TaskEvent,
    *,
    step_id: str,
    steps: list[ClassifyStep],
    auto_publish: bool = False,
) -> dict[str, object]:
    task_runtime = prepare_clustered_task_runtime(task)
    run_result = ClassifyStepRunner(steps).run(task_runtime.state, task_runtime.runtime)
    return write_classify_task_checkpoint(
        task_runtime.project_root,
        task_runtime.run_id,
        task,
        step_id,
        task_runtime.input_path,
        run_result,
        task_runtime.runtime.config,
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

    return state.items, state.event_records, StepResult(
        step="classify",
        item_count=len(state.items),
        output_path=str(config.output_path),
        meta={
            "events_output_path": str(config.events_output_path),
            "discarded_output_path": str(config.discarded_output_path),
            "event_count": len(state.events),
            "discarded_count": len(state.discarded),
            "merged_event_count": state.merged_event_count,
            "llm_model": config.llm.model,
            "embedding_model": config.embedding.model,
            "batch_size": config.batch_size,
            "batch_concurrency": config.batch_concurrency,
            "suspect_mode": config.suspect_mode,
        },
    )
