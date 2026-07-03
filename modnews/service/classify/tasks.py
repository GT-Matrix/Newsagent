from __future__ import annotations

from pathlib import Path

from modnews.core.task import TaskEvent
from modnews.service.classify.io import append_run_checkpoint, load_news_items, resolve_input_path
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews_pipeline.classify.stage import run_classification
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
    checkpoint_payload = {
        "run_id": run_id,
        "step_id": checkpoint_step_id,
        "task_id": task.id,
        "status": "succeeded",
        "input_refs": {"items": str(input_path)},
        "output_refs": {
            "news_with_events": str(config.classification.output_path),
            "events": str(config.classification.events_output_path),
            "discarded_news": str(config.classification.discarded_output_path),
            "legacy_checkpoint": str(config.classification.checkpoint_path) if config.classification.checkpoint_path else None,
        },
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
