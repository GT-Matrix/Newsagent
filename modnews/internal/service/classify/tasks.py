from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modnews.core.task import TaskEvent
from modnews.internal.service.pipeline.checkpoint import CheckpointManager
from modnews.repository.runs import RunRepository
from modnews_pipeline.classify.stage import run_classification
from modnews_pipeline.config import load_config
from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import NewsItem


def run_classify_task(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    run_id = task.pipeline_run_id or str(task.payload.get("run_id") or "manual")
    config = load_config(task.payload.get("config"))
    if task.payload.get("disable_classification"):
        config.classification.enabled = False
    input_path = Path(str(task.payload.get("input_path") or config.output_path)).resolve()
    items = _load_items(input_path)
    ctx = PipelineContext.create(config)
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    classified_items, events, result = run_classification(ctx, items, config.classification)

    checkpoint = CheckpointManager(project_root)
    checkpoint_payload = {
        "run_id": run_id,
        "step_id": "classify",
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
    checkpoint_path = checkpoint.write(run_id, "classify", task.id, checkpoint_payload)
    _append_run_checkpoint(project_root, run_id, checkpoint_path)
    return {"step": result.to_dict(), "checkpoint_path": str(checkpoint_path), "stats": checkpoint_payload["stats"]}


def _load_items(path: Path) -> list[NewsItem]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw["items"] if isinstance(raw, dict) and "items" in raw else raw
    if not isinstance(rows, list):
        raise ValueError(f"expected item list in {path}")
    items: list[NewsItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        items.append(
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
        )
    return items


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
