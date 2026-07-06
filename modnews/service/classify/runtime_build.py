from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from modnews.core.config import ClassificationConfig, PipelineConfig
from modnews.core.context import PipelineContext
from modnews.core.models import NewsItem

from .checkpoint import load_resume_state
from .io import load_news_items, resolve_resume_checkpoint_path, resolve_task_resume_checkpoint_path
from .llm_client import LlmClient
from .retriever import EventVectorRetriever
from .runner import ClassifyRuntime
from .state import ClassifyState
from .utils import prepare_item


@dataclass(frozen=True, slots=True)
class ResolvedClassifyStateInput:
    items: list[NewsItem]
    resume_checkpoint_path: Path | None
    input_path: Path | None = None


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


def resolve_classify_state_input(
    project_root: Path,
    run_id: str,
    *,
    items: list[NewsItem] | None = None,
    input_path: Path | None = None,
    configured_resume_checkpoint_path: Path | None = None,
    prefer_run_checkpoint: bool,
) -> ResolvedClassifyStateInput:
    resolved_items = list(items) if items is not None else load_news_items(_require_input_path(input_path))
    if prefer_run_checkpoint:
        resume_checkpoint_path = resolve_task_resume_checkpoint_path(project_root, run_id)
    else:
        resume_checkpoint_path = resolve_resume_checkpoint_path(project_root, run_id, configured_resume_checkpoint_path)
    return ResolvedClassifyStateInput(
        items=resolved_items,
        resume_checkpoint_path=resume_checkpoint_path,
        input_path=input_path.resolve() if input_path else None,
    )


def build_classify_state(project_root: Path, run_id: str, input_path: Path, configured_resume_checkpoint_path: Path | None = None) -> ClassifyState:
    return build_classify_state_from_resolved_input(
        resolve_classify_state_input(
            project_root,
            run_id,
            input_path=input_path,
            configured_resume_checkpoint_path=configured_resume_checkpoint_path,
            prefer_run_checkpoint=False,
        )
    )


def build_classify_state_for_run(project_root: Path, run_id: str, items: list[NewsItem]) -> ClassifyState:
    return build_classify_state_from_resolved_input(
        resolve_classify_state_input(
            project_root,
            run_id,
            items=items,
            prefer_run_checkpoint=True,
        )
    )


def build_classify_state_from_items(
    items: list[NewsItem],
    *,
    resume_checkpoint_path: Path | None,
) -> ClassifyState:
    return build_classify_state_from_resolved_input(
        ResolvedClassifyStateInput(
            items=list(items),
            resume_checkpoint_path=resume_checkpoint_path,
        )
    )


def build_classify_state_from_resolved_input(resolved: ResolvedClassifyStateInput) -> ClassifyState:
    resume_state = load_resume_state(resolved.resume_checkpoint_path, resolved.items)
    return ClassifyState(
        items=resume_state.items,
        prepared=[prepare_item(index, item) for index, item in enumerate(resume_state.items)],
        events=resume_state.events,
        discarded=resume_state.discarded,
        stage=resume_state.stage,
        processed_candidates=resume_state.processed_candidates,
    )


def _require_input_path(input_path: Path | None) -> Path:
    if input_path is None:
        raise ValueError("input_path is required when classify state items are not provided")
    return input_path
