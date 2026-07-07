from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from modnews.core.config import ClassificationConfig, PipelineConfig, load_config
from modnews.core.context import PipelineContext
from modnews.core.models import NewsItem
from modnews.core.task import TaskEvent

from .checkpoint import load_resume_state
from .io import (
    load_news_items,
    resolve_input_resume_checkpoint_path,
    resolve_resume_checkpoint_path,
    resolve_task_resume_checkpoint_path,
)
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


@dataclass(frozen=True, slots=True)
class ResolvedClassifyTaskEnvironment:
    project_root: Path
    run_id: str
    config: PipelineConfig
    ctx: PipelineContext


@dataclass(slots=True)
class ClassifyRuntimeFacade:
    def build_runtime(self, config: PipelineConfig, *, write_fixed_outputs: bool = True) -> ClassifyRuntime:
        ctx = PipelineContext.create(config)
        ctx.work_dir.mkdir(parents=True, exist_ok=True)
        return self.build_runtime_for_context(
            ctx,
            config.classification,
            write_fixed_outputs=write_fixed_outputs,
        )

    def build_runtime_for_context(
        self,
        ctx: PipelineContext,
        config: ClassificationConfig,
        *,
        write_fixed_outputs: bool = True,
    ) -> ClassifyRuntime:
        return ClassifyRuntime(
            ctx=ctx,
            config=config,
            client=self.build_llm_client_for_context(ctx, config),
            retriever=self.build_retriever_for_context(ctx, config),
            write_fixed_outputs=write_fixed_outputs,
        )

    def build_llm_client_for_context(self, ctx: PipelineContext, config: ClassificationConfig) -> LlmClient:
        return LlmClient(config.llm, ctx.session)

    def build_retriever_for_context(self, ctx: PipelineContext, config: ClassificationConfig) -> EventVectorRetriever:
        return EventVectorRetriever(config.embedding, ctx.session)

    def resolve_state_input(
        self,
        project_root: Path,
        run_id: str,
        *,
        items: list[NewsItem] | None = None,
        input_path: Path | None = None,
        configured_resume_checkpoint_path: Path | None = None,
        prefer_run_checkpoint: bool,
    ) -> ResolvedClassifyStateInput:
        resolved_items = list(items) if items is not None else load_news_items(self._require_input_path(input_path))
        if prefer_run_checkpoint:
            resume_checkpoint_path = resolve_task_resume_checkpoint_path(project_root, run_id)
            if resume_checkpoint_path is None:
                resume_checkpoint_path = resolve_input_resume_checkpoint_path(input_path)
        else:
            resume_checkpoint_path = resolve_resume_checkpoint_path(project_root, run_id, configured_resume_checkpoint_path)
        return ResolvedClassifyStateInput(
            items=resolved_items,
            resume_checkpoint_path=resume_checkpoint_path,
            input_path=input_path.resolve() if input_path else None,
        )

    def resolve_task_environment(self, task: TaskEvent) -> ResolvedClassifyTaskEnvironment:
        project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
        run_id = task.pipeline_run_id or str(task.payload.get("run_id") or "manual")
        config = load_config(task.payload.get("config"), project_root=project_root)
        ctx = PipelineContext.create(config)
        return ResolvedClassifyTaskEnvironment(
            project_root=project_root,
            run_id=run_id,
            config=config,
            ctx=ctx,
        )

    def build_state(self, project_root: Path, run_id: str, input_path: Path, configured_resume_checkpoint_path: Path | None = None) -> ClassifyState:
        return self.build_state_from_resolved_input(
            self.resolve_state_input(
                project_root,
                run_id,
                input_path=input_path,
                configured_resume_checkpoint_path=configured_resume_checkpoint_path,
                prefer_run_checkpoint=False,
            )
        )

    def build_state_for_run(self, project_root: Path, run_id: str, items: list[NewsItem]) -> ClassifyState:
        return self.build_state_from_resolved_input(
            self.resolve_state_input(
                project_root,
                run_id,
                items=items,
                prefer_run_checkpoint=True,
            )
        )

    def build_state_from_items(
        self,
        items: list[NewsItem],
        *,
        resume_checkpoint_path: Path | None,
    ) -> ClassifyState:
        return self.build_state_from_resolved_input(
            ResolvedClassifyStateInput(
                items=list(items),
                resume_checkpoint_path=resume_checkpoint_path,
            )
        )

    def build_state_from_resolved_input(self, resolved: ResolvedClassifyStateInput) -> ClassifyState:
        resume_state = load_resume_state(resolved.resume_checkpoint_path, resolved.items)
        return ClassifyState(
            items=resume_state.items,
            prepared=[prepare_item(index, item) for index, item in enumerate(resume_state.items)],
            events=resume_state.events,
            discarded=resume_state.discarded,
            stage=resume_state.stage,
            processed_candidates=resume_state.processed_candidates,
        )

    def _require_input_path(self, input_path: Path | None) -> Path:
        if input_path is None:
            raise ValueError("input_path is required when classify state items are not provided")
        return input_path
