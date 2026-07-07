from __future__ import annotations

from pathlib import Path

from modnews.core.config import ClassificationConfig, PipelineConfig
from modnews.core.context import PipelineContext
from modnews.core.models import NewsItem
from modnews.core.task import TaskEvent

from .llm_client import LlmClient
from .retriever import EventVectorRetriever
from .runtime_facade import (
    ClassifyRuntimeFacade,
    ResolvedClassifyStateInput,
    ResolvedClassifyTaskEnvironment,
)
from .runner import ClassifyRuntime
from .state import ClassifyState


_RUNTIME_FACADE = ClassifyRuntimeFacade()


def build_classify_runtime(config: PipelineConfig, *, write_fixed_outputs: bool = True) -> ClassifyRuntime:
    return _RUNTIME_FACADE.build_runtime(config, write_fixed_outputs=write_fixed_outputs)


def build_classify_runtime_for_context(
    ctx: PipelineContext,
    config: ClassificationConfig,
    *,
    write_fixed_outputs: bool = True,
) -> ClassifyRuntime:
    return _RUNTIME_FACADE.build_runtime_for_context(ctx, config, write_fixed_outputs=write_fixed_outputs)


def build_classify_llm_client_for_context(ctx: PipelineContext, config: ClassificationConfig) -> LlmClient:
    return _RUNTIME_FACADE.build_llm_client_for_context(ctx, config)


def build_classify_retriever_for_context(ctx: PipelineContext, config: ClassificationConfig) -> EventVectorRetriever:
    return _RUNTIME_FACADE.build_retriever_for_context(ctx, config)


def resolve_classify_state_input(
    project_root: Path,
    run_id: str,
    *,
    items: list[NewsItem] | None = None,
    input_path: Path | None = None,
    configured_resume_checkpoint_path: Path | None = None,
    prefer_run_checkpoint: bool,
) -> ResolvedClassifyStateInput:
    return _RUNTIME_FACADE.resolve_state_input(
        project_root,
        run_id,
        items=items,
        input_path=input_path,
        configured_resume_checkpoint_path=configured_resume_checkpoint_path,
        prefer_run_checkpoint=prefer_run_checkpoint,
    )


def resolve_classify_task_environment(task: TaskEvent) -> ResolvedClassifyTaskEnvironment:
    return _RUNTIME_FACADE.resolve_task_environment(task)


def build_classify_state(project_root: Path, run_id: str, input_path: Path, configured_resume_checkpoint_path: Path | None = None) -> ClassifyState:
    return _RUNTIME_FACADE.build_state(project_root, run_id, input_path, configured_resume_checkpoint_path)


def build_classify_state_for_run(project_root: Path, run_id: str, items: list[NewsItem]) -> ClassifyState:
    return _RUNTIME_FACADE.build_state_for_run(project_root, run_id, items)


def build_classify_state_from_items(
    items: list[NewsItem],
    *,
    resume_checkpoint_path: Path | None,
) -> ClassifyState:
    return _RUNTIME_FACADE.build_state_from_items(items, resume_checkpoint_path=resume_checkpoint_path)


def build_classify_state_from_resolved_input(resolved: ResolvedClassifyStateInput) -> ClassifyState:
    return _RUNTIME_FACADE.build_state_from_resolved_input(resolved)
