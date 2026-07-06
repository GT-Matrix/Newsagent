from __future__ import annotations

from pathlib import Path

from modnews.core.config import ClassificationConfig, PipelineConfig
from modnews.core.context import PipelineContext
from modnews.core.models import NewsItem

from .checkpoint import load_resume_state
from .llm_client import LlmClient
from .retriever import EventVectorRetriever
from .runner import ClassifyRuntime
from .state import ClassifyState
from .utils import prepare_item


def build_classify_runtime(config: PipelineConfig, *, write_fixed_outputs: bool = True) -> ClassifyRuntime:
    ctx = PipelineContext.create(config)
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    return build_classify_runtime_for_context(
        ctx,
        config.classification,
        write_fixed_outputs=write_fixed_outputs,
    )


def build_classify_runtime_for_context(
    ctx: PipelineContext,
    config: ClassificationConfig,
    *,
    write_fixed_outputs: bool = True,
) -> ClassifyRuntime:
    return ClassifyRuntime(
        ctx=ctx,
        config=config,
        client=LlmClient(config.llm, ctx.session),
        retriever=EventVectorRetriever(config.embedding, ctx.session),
        write_fixed_outputs=write_fixed_outputs,
    )


def build_classify_state(project_root: Path, run_id: str, input_path: Path, output_path: Path) -> ClassifyState:
    from .io import load_news_items

    items = load_news_items(input_path)
    return build_classify_state_for_run(project_root, run_id, items)


def build_classify_state_for_run(project_root: Path, run_id: str, items: list[NewsItem]) -> ClassifyState:
    from .io import resolve_task_resume_checkpoint_path

    resume_checkpoint_path = resolve_task_resume_checkpoint_path(project_root, run_id)
    return build_classify_state_from_items(items, resume_checkpoint_path=resume_checkpoint_path)


def build_classify_state_from_items(
    items: list[NewsItem],
    *,
    resume_checkpoint_path: Path | None,
) -> ClassifyState:
    resume_state = load_resume_state(resume_checkpoint_path, items)
    return ClassifyState(
        items=resume_state.items,
        prepared=[prepare_item(index, item) for index, item in enumerate(resume_state.items)],
        events=resume_state.events,
        discarded=resume_state.discarded,
        stage=resume_state.stage,
        processed_candidates=resume_state.processed_candidates,
    )
