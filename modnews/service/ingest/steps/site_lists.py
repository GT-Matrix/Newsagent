from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from modnews.core.context import PipelineContext
from modnews.core.models import NewsItem, StepResult
from modnews.core.task import TaskEvent
from modnews.repository.source_config import source_config_store
from modnews.service.extraction.task_registry import (
    build_registered_web_source_task,
    get_registered_extraction_task,
)

from modnews.service.ingest.base import IngestStep

class SiteListsStep(IngestStep):
    step_name = "site_lists"

    @classmethod
    def options_from_api_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        options = super().options_from_api_payload(payload)
        sites = payload.get("sites")
        if isinstance(sites, list):
            options["sites"] = [str(item) for item in sites if item]
        if payload.get("limit_per_site") is not None:
            options["limit_per_site"] = payload.get("limit_per_site")
        if payload.get("max_concurrency") is not None:
            options["max_concurrency"] = payload.get("max_concurrency")
        return options

    @classmethod
    def options_from_cli_args(cls, args: argparse.Namespace) -> dict[str, Any]:
        options: dict[str, Any] = {}
        sites = getattr(args, "sites", None)
        if sites:
            options["sites"] = sites
        limit_per_site = getattr(args, "limit_per_site", None)
        if limit_per_site is not None:
            options["limit_per_site"] = limit_per_site
        max_concurrency = getattr(args, "max_concurrency", None)
        if max_concurrency is not None:
            options["max_concurrency"] = max_concurrency
        return options

    @classmethod
    def plan_tasks(
        cls,
        *,
        project_root: Path,
        run_id: str,
        config_path: object = None,
        options: dict[str, Any] | None = None,
    ) -> list[TaskEvent]:
        source_config = source_config_store(project_root).load()
        step_config = source_config.get("steps", {}).get(cls.step_name, {})
        if isinstance(step_config, dict) and not step_config.get("enabled", True):
            return []
        task_options = options if isinstance(options, dict) else {}
        requested_sites = task_options.get("sites") or (step_config.get("sites") if isinstance(step_config, dict) else None) or []
        requested = {str(item) for item in requested_sites if item}
        limit = int(task_options.get("limit_per_site") or (step_config.get("limit_per_site") if isinstance(step_config, dict) else 10) or 10)
        max_concurrency = int(task_options.get("max_concurrency") or (step_config.get("max_concurrency") if isinstance(step_config, dict) else 4) or 4)
        raw_sources = source_config.get("sources", {}).get(cls.step_name, {})
        tasks: list[TaskEvent] = []
        if not isinstance(raw_sources, dict):
            return tasks
        spec = get_registered_extraction_task("web_source.run")
        for source_id, raw in raw_sources.items():
            if requested and source_id not in requested:
                continue
            if not isinstance(raw, dict) or not bool(raw.get("enabled", True)):
                continue
            tasks.append(
                build_registered_web_source_task(
                    spec,
                    project_root=project_root,
                    run_id=run_id,
                    source_id=source_id,
                    config_path=config_path,
                    limit=limit,
                    max_concurrency=max_concurrency,
                )
            )
        return tasks

    def run(self, ctx: PipelineContext) -> tuple[list[NewsItem], StepResult]:
        raise ValueError("site_lists is task-only and must be planned as per-source web_source.run tasks")
