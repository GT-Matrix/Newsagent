from __future__ import annotations

import json
from pathlib import Path

from modnews.core.task import TaskEvent
from modnews.service.classify.io import append_run_checkpoint, load_news_items, resolve_input_path
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews.service.classify.checkpoint import build_checkpoint_meta, write_run_output_artifacts
from modnews.service.classify.stage import run_classification
from modnews.service.classify.types import DiscardedRecord
from modnews.core.config import load_config
from modnews.core.context import PipelineContext


def run_classify_task(task: TaskEvent) -> dict[str, object]:
    return run_clustered_pipeline_task(task, checkpoint_step_id="classify")


def run_clustered_pipeline_task(task: TaskEvent, *, checkpoint_step_id: str = "classify/clustered_pipeline") -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    run_id = task.pipeline_run_id or str(task.payload.get("run_id") or "manual")
    config = load_config(task.payload.get("config"))
    if task.payload.get("disable_classification"):
        config.classification.enabled = False
    input_path = resolve_input_path(project_root, run_id, task.payload.get("input_path"), config.output_path)
    items = load_news_items(input_path)
    ctx = PipelineContext.create(config)
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    classified_items, events, result = run_classification(ctx, items, config.classification)

    checkpoint = CheckpointManager(project_root)
    discarded = _load_discarded_records(config.classification.discarded_output_path)
    meta = build_checkpoint_meta(
        classified_items,
        events,
        discarded,
        stage="clustered_pipeline",
        merged_event_count=result.meta.get("merged_event_count") if isinstance(result.meta.get("merged_event_count"), int) else None,
    )
    output_refs = write_run_output_artifacts(checkpoint, run_id, checkpoint_step_id, task.id, classified_items, events, discarded, meta)
    checkpoint_payload = {
        "run_id": run_id,
        "step_id": checkpoint_step_id,
        "task_id": task.id,
        "status": "succeeded",
        "input_refs": {"items": str(input_path)},
        "output_refs": output_refs,
        "stats": {
            "item_count": len(classified_items),
            "event_count": len(events),
            "discarded_count": result.meta.get("discarded_count"),
        },
        "error": None,
    }
    checkpoint_path = checkpoint.write(run_id, checkpoint_step_id, task.id, checkpoint_payload)
    append_run_checkpoint(project_root, run_id, checkpoint_path)
    return {
        "step": result.to_dict(),
        "checkpoint_path": str(checkpoint_path),
        "auto_publish_checkpoint": str(checkpoint_path),
        "stats": checkpoint_payload["stats"],
    }


def _load_discarded_records(path: Path) -> list[DiscardedRecord]:
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        return []
    records: list[DiscardedRecord] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        records.append(
            DiscardedRecord(
                index=int(row.get("index") or 0),
                title=str(row.get("title") or ""),
                platform=str(row.get("platform") or ""),
                stage=str(row.get("stage") or ""),
                reason=str(row.get("reason") or ""),
            )
        )
    return records
