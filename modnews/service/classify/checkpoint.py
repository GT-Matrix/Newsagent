from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from modnews.core.config import ClassificationConfig
from modnews.core.models import EventRecord, NewsItem
from modnews.core.progress import emit
from modnews.service.pipeline.checkpoint import CheckpointManager

from .state_codec import build_output_payloads, decode_resume_state
from .types import DiscardedRecord, ResumeState


def write_outputs(
    config: ClassificationConfig,
    items: list[NewsItem],
    events: list[EventRecord],
    discarded: list[DiscardedRecord],
    checkpoint_meta: dict[str, object] | None = None,
) -> None:
    payloads = build_output_payloads(items, events, discarded, checkpoint_meta)
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.events_output_path.parent.mkdir(parents=True, exist_ok=True)
    config.discarded_output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(
        json.dumps(payloads["news_with_events"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    config.events_output_path.write_text(
        json.dumps(payloads["events"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    config.discarded_output_path.write_text(
        json.dumps(payloads["discarded_news"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    checkpoint_path = config.checkpoint_path or (config.output_path.parent / "classification_progress.json")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_payload = payloads["classification_progress"]
    checkpoint_path.write_text(
        json.dumps(checkpoint_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    emit("checkpoint", path=str(checkpoint_path), meta=checkpoint_payload["meta"])


def write_run_output_artifacts(
    checkpoint: CheckpointManager,
    run_id: str,
    step_id: str,
    task_id: str,
    items: list[NewsItem],
    events: list[EventRecord],
    discarded: list[DiscardedRecord],
    checkpoint_meta: dict[str, object] | None = None,
) -> dict[str, str]:
    payloads = build_output_payloads(items, events, discarded, checkpoint_meta)
    return {
        "news_with_events": str(checkpoint.write_artifact(run_id, step_id, task_id, "news_with_events.json", payloads["news_with_events"])),
        "events": str(checkpoint.write_artifact(run_id, step_id, task_id, "events.json", payloads["events"])),
        "discarded_news": str(checkpoint.write_artifact(run_id, step_id, task_id, "discarded_news.json", payloads["discarded_news"])),
        "classification_progress": str(
            checkpoint.write_artifact(run_id, step_id, task_id, "classification_progress.json", payloads["classification_progress"])
        ),
    }


def load_resume_state(checkpoint_path: Path | None, items: list[NewsItem]) -> ResumeState:
    if not checkpoint_path or not checkpoint_path.exists():
        return ResumeState(items=items, events=[], discarded=[], stage="started")
    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    return decode_resume_state(payload, items)


def build_checkpoint_meta(
    items: list[NewsItem],
    events: list[EventRecord],
    discarded: list[DiscardedRecord],
    *,
    stage: str,
    processed_candidates: int | None = None,
    total_candidates: int | None = None,
    merged_event_count: int | None = None,
) -> dict[str, object]:
    return {
        "stage": stage,
        "item_count": len(items),
        "event_count": len(events),
        "discarded_count": len(discarded),
        "processed_candidates": processed_candidates,
        "total_candidates": total_candidates,
        "merged_event_count": merged_event_count,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
