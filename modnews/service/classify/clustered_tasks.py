from __future__ import annotations

from pathlib import Path

from modnews.core.task import TaskEvent
from modnews.service.classify.io import append_run_checkpoint, load_news_items, resolve_input_path
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews.service.classify.checkpoint import build_checkpoint_meta, load_resume_state, write_outputs, write_run_output_artifacts
from modnews.service.classify.llm_client import LlmClient
from modnews.service.classify.retriever import EventVectorRetriever
from modnews.service.classify.runner import ClassifyRuntime
from modnews.service.classify.state import ClassifyState
from modnews.service.classify.steps import ClusteredEventExtractionStep, ClusteredEventMergeStep, StartCheckpointStep
from modnews.service.classify.utils import prepare_item
from modnews.core.config import load_config
from modnews.core.context import PipelineContext


def run_clustered_event_extraction_task(task: TaskEvent) -> dict[str, object]:
    project_root, run_id, input_path, state, runtime = _prepare(task)
    start_step = StartCheckpointStep()
    if start_step.should_run(state):
        state = start_step.run(state, runtime)
    step = ClusteredEventExtractionStep()
    if step.should_run(state):
        state = step.run(state, runtime)
        state.stage = step.output_stage
    return _write_run_checkpoint(
        project_root,
        run_id,
        task,
        "classify/clustered_event_extraction",
        input_path,
        state,
        runtime,
    )


def run_clustered_event_merge_task(task: TaskEvent) -> dict[str, object]:
    project_root, run_id, input_path, state, runtime = _prepare(task)
    step = ClusteredEventMergeStep()
    if step.should_run(state):
        state = step.run(state, runtime)
        state.stage = step.output_stage
    return _write_run_checkpoint(
        project_root,
        run_id,
        task,
        "classify/clustered_event_merge",
        input_path,
        state,
        runtime,
        auto_publish=True,
    )


def _prepare(task: TaskEvent) -> tuple[Path, str, Path, ClassifyState, ClassifyRuntime]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    run_id = task.pipeline_run_id or str(task.payload.get("run_id") or "manual")
    config = load_config(task.payload.get("config"))
    input_path = resolve_input_path(project_root, run_id, task.payload.get("input_path"), config.output_path)
    items = load_news_items(input_path)
    ctx = PipelineContext.create(config)
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    resume_state = load_resume_state(config.classification.checkpoint_path, items)
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
        config=config.classification,
        client=LlmClient(config.classification.llm, ctx.session),
        retriever=EventVectorRetriever(config.classification.embedding, ctx.session),
    )
    return project_root, run_id, input_path, state, runtime


def _write_run_checkpoint(
    project_root: Path,
    run_id: str,
    task: TaskEvent,
    step_id: str,
    input_path: Path,
    state: ClassifyState,
    runtime: ClassifyRuntime,
    *,
    auto_publish: bool = False,
) -> dict[str, object]:
    checkpoint = CheckpointManager(project_root)
    meta = build_checkpoint_meta(
        state.items,
        state.event_records,
        state.discarded,
        stage=state.stage,
        processed_candidates=state.processed_candidates,
        total_candidates=state.total_candidates,
        merged_event_count=state.merged_event_count,
    )
    write_outputs(runtime.config, state.items, state.event_records, state.discarded, meta)
    output_refs = write_run_output_artifacts(checkpoint, run_id, step_id, task.id, state.items, state.event_records, state.discarded, meta)
    checkpoint_payload = {
        "run_id": run_id,
        "step_id": step_id,
        "task_id": task.id,
        "status": "succeeded",
        "input_refs": {"items": str(input_path)},
        "output_refs": output_refs,
        "stats": {
            "item_count": len(state.items),
            "event_count": len(state.events),
            "discarded_count": len(state.discarded),
            "merged_event_count": state.merged_event_count,
        },
        "error": None,
    }
    checkpoint_path = checkpoint.write(run_id, step_id, task.id, checkpoint_payload)
    append_run_checkpoint(project_root, run_id, checkpoint_path)
    result: dict[str, object] = {
        "checkpoint_path": str(checkpoint_path),
        "stats": checkpoint_payload["stats"],
    }
    if auto_publish:
        result["auto_publish_checkpoint"] = str(checkpoint_path)
    return result
