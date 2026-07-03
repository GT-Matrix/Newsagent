from __future__ import annotations

import json
from pathlib import Path

from modnews.repository.runs import RunRepository
from modnews.core.models import NewsItem


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


def resolve_resume_checkpoint_path(project_root: Path, run_id: str, configured_path: Path | None) -> Path | None:
    artifact_path = _latest_run_classification_progress(project_root, run_id)
    if artifact_path:
        return artifact_path
    return configured_path if configured_path and configured_path.exists() else None


def resolve_task_resume_checkpoint_path(project_root: Path, run_id: str) -> Path | None:
    return _latest_run_classification_progress(project_root, run_id)


def _latest_run_classification_progress(project_root: Path, run_id: str) -> Path | None:
    try:
        checkpoints = RunRepository(project_root).get(run_id).get("checkpoints", [])
    except KeyError:
        return None
    for checkpoint_value in reversed([value for value in checkpoints if value]):
        checkpoint_path = Path(str(checkpoint_value)).expanduser().resolve()
        if not checkpoint_path.exists():
            continue
        try:
            checkpoint_payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(checkpoint_payload, dict):
            continue
        output_refs = checkpoint_payload.get("output_refs")
        if not isinstance(output_refs, dict):
            continue
        artifact_value = output_refs.get("classification_progress")
        if not artifact_value:
            continue
        artifact_path = Path(str(artifact_value)).expanduser().resolve()
        if artifact_path.exists():
            return artifact_path
    return None


def append_run_checkpoint(project_root: Path, run_id: str, checkpoint_path: Path) -> None:
    RunRepository(project_root).append_checkpoint(run_id, checkpoint_path, create_payload={"source": "manual_classify_task"})
