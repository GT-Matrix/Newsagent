from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from modnews.core.config import PipelineConfig, load_config
from modnews.core.context import PipelineContext
from modnews.core.task import TaskEvent

from .checkpoint import load_resume_state
from .llm_client import LlmClient
from .retriever import EventVectorRetriever
from .runner import ClassifyRuntime
from .state import ClassifyState
from .utils import prepare_item
from .io import load_news_items, resolve_input_path, resolve_task_resume_checkpoint_path


@dataclass(slots=True)
class ClusteredTaskRuntime:
    project_root: Path
    run_id: str
    input_path: Path
    state: ClassifyState
    runtime: ClassifyRuntime


def prepare_clustered_task_runtime(task: TaskEvent) -> ClusteredTaskRuntime:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    run_id = task.pipeline_run_id or str(task.payload.get("run_id") or "manual")
    config = load_config(task.payload.get("config"), project_root=project_root)
    input_path = resolve_input_path(project_root, run_id, task.payload.get("input_path"), config.output_path)
    items = load_news_items(input_path)
    state = _build_state(project_root, run_id, items)
    runtime = build_classify_runtime(config, write_fixed_outputs=bool(task.payload.get("write_fixed_outputs")))
    return ClusteredTaskRuntime(
        project_root=project_root,
        run_id=run_id,
        input_path=input_path,
        state=state,
        runtime=runtime,
    )


def build_classify_runtime(config: PipelineConfig, *, write_fixed_outputs: bool = True) -> ClassifyRuntime:
    ctx = PipelineContext.create(config)
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    return ClassifyRuntime(
        ctx=ctx,
        config=config.classification,
        client=LlmClient(config.classification.llm, ctx.session),
        retriever=EventVectorRetriever(config.classification.embedding, ctx.session),
        write_fixed_outputs=write_fixed_outputs,
    )


def build_classify_state(project_root: Path, run_id: str, input_path: Path, output_path: Path) -> ClassifyState:
    items = load_news_items(input_path)
    return _build_state(project_root, run_id, items)


def _build_state(project_root: Path, run_id: str, items) -> ClassifyState:
    resume_checkpoint_path = resolve_task_resume_checkpoint_path(project_root, run_id)
    resume_state = load_resume_state(resume_checkpoint_path, items)
    return ClassifyState(
        items=resume_state.items,
        prepared=[prepare_item(index, item) for index, item in enumerate(resume_state.items)],
        events=resume_state.events,
        discarded=resume_state.discarded,
        stage=resume_state.stage,
        processed_candidates=resume_state.processed_candidates,
    )
