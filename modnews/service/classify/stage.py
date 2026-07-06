from __future__ import annotations

from modnews.core.config import ClassificationConfig
from modnews.core.context import PipelineContext
from modnews.core.models import EventRecord, NewsItem, StepResult

from .runner import ClassifyRuntime, ClassifyStepRunner
from .runtime_build import build_classify_runtime_for_context, build_classify_state_from_items
from .steps import build_full_classify_steps


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
    run_result = _build_runner().run(state, runtime)
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


def _build_runner() -> ClassifyStepRunner:
    return ClassifyStepRunner(build_full_classify_steps())
