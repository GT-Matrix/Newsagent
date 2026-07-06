from __future__ import annotations

from modnews.core.config import ClassificationConfig
from modnews.core.context import PipelineContext
from modnews.core.models import EventRecord, NewsItem, StepResult

from .run_result import build_classify_step_result
from .runner import ClassifyStepRunner
from .runtime_build import (
    build_classify_runtime_for_context,
    build_classify_state_from_resolved_input,
    resolve_classify_state_input,
)
from .step_observer import EmittingClassifyStepObserver
from .steps import get_registered_classify_flow


def run_classification(
    ctx: PipelineContext,
    items: list[NewsItem],
    config: ClassificationConfig,
) -> tuple[list[NewsItem], list[EventRecord], StepResult]:
    if not config.enabled:
        return items, [], StepResult(step="classify", item_count=len(items), meta={"enabled": False})

    resolved_state_input = resolve_classify_state_input(
        ctx.config.project_root,
        "manual",
        items=items,
        configured_resume_checkpoint_path=config.checkpoint_path,
        prefer_run_checkpoint=False,
    )
    state = build_classify_state_from_resolved_input(resolved_state_input)
    runtime = build_classify_runtime_for_context(ctx, config)
    run_result = ClassifyStepRunner(
        get_registered_classify_flow("full").build_steps(),
        observer=EmittingClassifyStepObserver(),
    ).run(state, runtime)
    state = run_result.state

    return state.items, state.event_records, build_classify_step_result(
        config=config,
        run_result=run_result,
        step="classify",
    )
