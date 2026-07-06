from __future__ import annotations

from modnews.core.config import ClassificationConfig
from modnews.core.context import PipelineContext
from modnews.core.models import EventRecord, NewsItem, StepResult

from .checkpoint import load_resume_state
from .llm_client import LlmClient
from .retriever import EventVectorRetriever
from .runner import ClassifyRuntime, ClassifyStepRunner
from .state import ClassifyState
from .steps import build_full_classify_steps
from .utils import prepare_item


def run_classification(
    ctx: PipelineContext,
    items: list[NewsItem],
    config: ClassificationConfig,
) -> tuple[list[NewsItem], list[EventRecord], StepResult]:
    if not config.enabled:
        return items, [], StepResult(step="classify", item_count=len(items), meta={"enabled": False})

    resume_state = load_resume_state(config.checkpoint_path, items)
    state = ClassifyState(
        items=resume_state.items,
        prepared=[prepare_item(index, item) for index, item in enumerate(resume_state.items)],
        events=resume_state.events,
        discarded=resume_state.discarded,
        stage=resume_state.stage,
        processed_candidates=resume_state.processed_candidates,
    )
    runtime = ClassifyRuntime(
        ctx=ctx,
        config=config,
        client=LlmClient(config.llm, ctx.session),
        retriever=EventVectorRetriever(config.embedding, ctx.session),
    )
    state = _build_runner().run(state, runtime)

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
