from __future__ import annotations

from modnews.core.models import StepResult
from modnews.core.config import ClassificationConfig

from .runner import ClassifyRunResult
from .task_result import build_classify_run_stats


def build_classify_step_result(
    *,
    config: ClassificationConfig,
    run_result: ClassifyRunResult,
    step: str = "classify",
) -> StepResult:
    state = run_result.state
    stats = build_classify_run_stats(run_result)
    return StepResult(
        step=step,
        item_count=len(state.items),
        output_path=str(config.output_path),
        meta={
            "events_output_path": str(config.events_output_path),
            "discarded_output_path": str(config.discarded_output_path),
            "event_count": stats["event_count"],
            "discarded_count": stats["discarded_count"],
            "merged_event_count": stats["merged_event_count"],
            "llm_model": config.llm.model,
            "embedding_model": config.embedding.model,
            "batch_size": config.batch_size,
            "batch_concurrency": config.batch_concurrency,
        },
    )
