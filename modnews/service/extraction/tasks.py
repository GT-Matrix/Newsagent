from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from modnews.core.task import TaskBlocked, TaskEvent
from modnews.repository.runs import RunRepository
from modnews.repository.source_config import source_config_store
from modnews.service.extraction.orchestrator import WebExtractionOrchestrator
from modnews.service.extraction.web_contract import WebSource
from modnews.service.pipeline.checkpoint import CheckpointManager


def run_web_source_task(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    source_id = str(task.payload["source_id"])
    run_id = task.pipeline_run_id or str(task.payload.get("run_id") or "manual")
    config = source_config_store(project_root).load()
    raw = config.get("sources", {}).get("site_lists", {}).get(source_id)
    if not isinstance(raw, dict):
        raise ValueError(f"source not found: {source_id}")
    source = WebSource.from_config(source_id, raw)
    if not source.enabled:
        raise ValueError(f"source is disabled: {source_id}")
    limit = int(task.payload.get("limit") or config.get("steps", {}).get("site_lists", {}).get("limit_per_site", 10))
    scrape_date = str(task.payload.get("scrape_date") or datetime.now().astimezone().isoformat(timespec="seconds"))
    job = WebExtractionOrchestrator(project_root).run_source(source, scrape_date=scrape_date, limit=limit)
    if job.state == "skipped_unrepairable":
        raise TaskBlocked(
            job.error or f"web source {source_id} is blocked",
            details={"job": job.to_dict(), "error_type": job.error_type},
        )
    if job.state in {"repair_queued", "repairing"}:
        raise TaskBlocked(
            job.error or f"web source {source_id} requires extractor repair",
            details={"job": job.to_dict(), "repair_task_id": job.repair_task_id},
        )
    checkpoint = CheckpointManager(project_root)
    rows = []
    if job.output_path:
        try:
            payload = json.loads(Path(job.output_path).read_text(encoding="utf-8"))
            rows = payload if isinstance(payload, list) else []
        except Exception:
            rows = []
    artifact_path = checkpoint.write_artifact(run_id, f"ingest/site_lists/{source_id}", task.id, "items.json", rows)
    checkpoint_payload = {
        "run_id": run_id,
        "step_id": f"ingest/site_lists/{source_id}",
        "task_id": task.id,
        "status": "succeeded",
        "input_refs": {},
        "output_refs": {
            "items": str(artifact_path),
            **({"job_output": str(job.output_path)} if job.output_path else {}),
        },
        "stats": {"item_count": len(rows), "job_id": job.id},
        "error": None,
    }
    checkpoint_path = checkpoint.write(run_id, f"ingest/site_lists/{source_id}", task.id, checkpoint_payload)
    RunRepository(project_root).append_checkpoint(run_id, checkpoint_path, create_payload={"source": "web_source_task"})
    return {
        "job": job.to_dict(),
        "checkpoint_path": str(checkpoint_path),
        "artifact_path": str(artifact_path),
        "item_count": len(rows),
    }
