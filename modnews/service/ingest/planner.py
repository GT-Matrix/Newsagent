from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.core.task import TaskEvent
from modnews.repository.source_config import source_config_store


def plan_ingest_tasks(
    *,
    project_root: Path,
    step_id: str,
    run_id: str | None = None,
    config_path: object = None,
    options: dict[str, Any] | None = None,
) -> list[TaskEvent]:
    task_run_id = run_id or f"ingest-{step_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    task_options = options if isinstance(options, dict) else {}
    if step_id == "site_lists":
        return plan_site_list_source_tasks(
            project_root=project_root,
            run_id=task_run_id,
            config_path=config_path,
            options=task_options,
        )
    return [
        TaskEvent(
            id=f"ingest-{task_run_id}-{step_id}",
            type="ingest.run_step",
            pipeline_run_id=task_run_id,
            step_id=f"ingest/{step_id}",
            payload={
                "project_root": str(project_root),
                "run_id": task_run_id,
                "config": config_path,
                "step_id": step_id,
                "options": task_options,
            },
            concurrency_key=f"ingest:{step_id}",
            max_concurrency=1,
        )
    ]


def plan_site_list_source_tasks(
    *,
    project_root: Path,
    run_id: str,
    config_path: object = None,
    options: dict[str, Any] | None = None,
) -> list[TaskEvent]:
    source_config = source_config_store(project_root).load()
    step_config = source_config.get("steps", {}).get("site_lists", {})
    if isinstance(step_config, dict) and not step_config.get("enabled", True):
        return []
    task_options = options if isinstance(options, dict) else {}
    requested_sites = task_options.get("sites") or (step_config.get("sites") if isinstance(step_config, dict) else None) or []
    requested = {str(item) for item in requested_sites if item}
    limit = int(task_options.get("limit_per_site") or (step_config.get("limit_per_site") if isinstance(step_config, dict) else 10) or 10)
    max_concurrency = int(task_options.get("max_concurrency") or (step_config.get("max_concurrency") if isinstance(step_config, dict) else 4) or 4)
    raw_sources = source_config.get("sources", {}).get("site_lists", {})
    tasks: list[TaskEvent] = []
    if not isinstance(raw_sources, dict):
        return tasks
    for source_id, raw in raw_sources.items():
        if requested and source_id not in requested:
            continue
        if not isinstance(raw, dict) or not bool(raw.get("enabled", True)):
            continue
        tasks.append(
            TaskEvent(
                id=f"web-source-{run_id}-{source_id}",
                type="web_source.run",
                pipeline_run_id=run_id,
                step_id=f"ingest/site_lists/{source_id}",
                payload={
                    "project_root": str(project_root),
                    "run_id": run_id,
                    "config": config_path,
                    "source_id": source_id,
                    "limit": limit,
                },
                concurrency_key="web_source",
                max_concurrency=max(1, max_concurrency),
                max_attempts=1,
            )
        )
    return tasks
