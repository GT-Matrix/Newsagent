from __future__ import annotations

import json
from pathlib import Path

from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews_pipeline.classify.checkpoint import build_checkpoint_meta, load_resume_state, write_outputs
from modnews_pipeline.classify.llm_client import LlmClient
from modnews_pipeline.classify.retriever import EventVectorRetriever
from modnews_pipeline.classify.runner import ClassifyRuntime
from modnews_pipeline.classify.state import ClassifyState
from modnews_pipeline.classify.steps import ClusteredEventExtractionStep, ClusteredEventMergeStep, StartCheckpointStep
from modnews_pipeline.classify.utils import prepare_item
from modnews_pipeline.config import load_config
from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import NewsItem


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
    input_ref = str(task.payload.get("input_path") or config.output_path)
    if input_ref == "__combined_ingest__":
        input_ref = str(RunRepository(project_root).get(run_id).get("combined_ingest_path") or config.output_path)
    input_path = Path(input_ref).resolve()
    items = _load_items(input_path)
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
    checkpoint_payload = {
        "run_id": run_id,
        "step_id": step_id,
        "task_id": task.id,
        "status": "succeeded",
        "input_refs": {"items": str(input_path)},
        "output_refs": {
            "news_with_events": str(runtime.config.output_path),
            "events": str(runtime.config.events_output_path),
            "discarded_news": str(runtime.config.discarded_output_path),
            "legacy_checkpoint": str(runtime.config.checkpoint_path) if runtime.config.checkpoint_path else None,
        },
        "stats": {
            "item_count": len(state.items),
            "event_count": len(state.events),
            "discarded_count": len(state.discarded),
            "merged_event_count": state.merged_event_count,
        },
        "error": None,
    }
    checkpoint_path = checkpoint.write(run_id, step_id, task.id, checkpoint_payload)
    _append_run_checkpoint(project_root, run_id, checkpoint_path)
    result: dict[str, object] = {
        "checkpoint_path": str(checkpoint_path),
        "stats": checkpoint_payload["stats"],
    }
    if auto_publish:
        result["auto_publish_checkpoint"] = str(checkpoint_path)
    return result


def _load_items(path: Path) -> list[NewsItem]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw["items"] if isinstance(raw, dict) and "items" in raw else raw
    if not isinstance(rows, list):
        raise ValueError(f"expected item list in {path}")
    return [
        NewsItem(
            platform=str(row["platform"]),
            title=str(row["title"]),
            url=str(row["url"]),
            pubtime=row.get("pubtime"),
            scrape_date=str(row["scrape_date"]),
            event_id=row.get("event_id"),
            event_label=row.get("event_label"),
            event_confidence=row.get("event_confidence"),
            is_ai_relevant=row.get("is_ai_relevant"),
            relevance_score=row.get("relevance_score"),
            canonical_summary=row.get("canonical_summary"),
            entities=row.get("entities") or [],
            event_type=row.get("event_type"),
            classification_decision=row.get("classification_decision"),
            classification_reason=row.get("classification_reason"),
        )
        for row in rows
        if isinstance(row, dict)
    ]


def _append_run_checkpoint(project_root: Path, run_id: str, checkpoint_path: Path) -> None:
    runs = RunRepository(project_root)
    try:
        record = runs.get(run_id)
    except KeyError:
        runs.create(run_id, {"source": "manual_classify_task"})
        record = runs.get(run_id)
    checkpoints = list(record.get("checkpoints", []))
    checkpoints.append(str(checkpoint_path))
    runs.update(run_id, checkpoints=checkpoints)
