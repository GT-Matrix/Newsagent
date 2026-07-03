from __future__ import annotations

from datetime import datetime
from pathlib import Path

from modnews.core.task import TaskEvent
from modnews_pipeline.sources import source_config_store
from modnews_pipeline.web_extraction.contract import WebSource
from modnews_pipeline.web_extraction.orchestrator import WebExtractionOrchestrator


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
    return {"job": job.to_dict()}
