from __future__ import annotations

from datetime import datetime
from pathlib import Path

from modnews.core.task import TaskBlocked, TaskEvent
from modnews.service.extraction.orchestrator import WebExtractionOrchestrator
from modnews.service.extraction.web_contract import WebSource
from modnews.repository.source_config import source_config_store


def run_web_source_task(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    source_id = str(task.payload["source_id"])
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
    return {"job": job.to_dict()}
