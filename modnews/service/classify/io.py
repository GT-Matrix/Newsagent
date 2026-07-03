from __future__ import annotations

import json
from pathlib import Path

from modnews.repository.runs import RunRepository
from modnews_pipeline.models import NewsItem


def resolve_input_path(project_root: Path, run_id: str, input_ref: object, fallback: Path) -> Path:
    ref = str(input_ref or fallback)
    if ref == "__combined_ingest__":
        ref = str(RunRepository(project_root).get(run_id).get("combined_ingest_path") or fallback)
    return Path(ref).resolve()


def load_news_items(path: Path) -> list[NewsItem]:
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


def append_run_checkpoint(project_root: Path, run_id: str, checkpoint_path: Path) -> None:
    runs = RunRepository(project_root)
    try:
        record = runs.get(run_id)
    except KeyError:
        runs.create(run_id, {"source": "manual_classify_task"})
        record = runs.get(run_id)
    checkpoints = list(record.get("checkpoints", []))
    checkpoints.append(str(checkpoint_path))
    runs.update(run_id, checkpoints=checkpoints)
