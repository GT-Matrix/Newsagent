from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modnews.core.task import TaskEvent
from modnews.core.context import PipelineContext
from modnews.core.models import NewsItem, StepResult
from modnews.repository.source_config import source_config_store
from modnews.service.extraction.orchestrator import WebExtractionOrchestrator

from modnews.service.ingest.base import IngestStep

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
)


class SiteListsStep(IngestStep):
    step_name = "site_lists"

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
                    step_id=f"ingest/{cls.step_name}/{source_id}",
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

    def run(self, ctx: PipelineContext) -> tuple[list[NewsItem], StepResult]:
        mock_url = ctx.config.site_lists_api_url
        if mock_url:
            return _run_via_mock(ctx, mock_url)

        return WebExtractionOrchestrator(ctx.config.project_root).run_pipeline_step(ctx, self.options)


def _run_via_mock(ctx: PipelineContext, api_url: str) -> tuple[list[NewsItem], StepResult]:
    resp = ctx.session.get(api_url, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    items = [
        NewsItem(
            platform=(row.get("platform") or "").strip(),
            title=(row.get("title") or "").strip(),
            url=row.get("url", ""),
            pubtime=row.get("pubtime"),
            scrape_date=row.get("scrape_date") or ctx.scrape_date,
        )
        for row in payload.get("items", [])
    ]
    output_path = ctx.work_dir / "site_lists_items.json"
    output_path.write_text(
        json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    raw_path = ctx.work_dir / "site_lists_raw.json"
    raw_path.write_text(json.dumps({"mock_api_url": api_url}, ensure_ascii=False, indent=2), encoding="utf-8")
    ctx.artifacts["site_lists"] = output_path
    ctx.artifacts["site_lists_raw"] = raw_path
    return items, StepResult(
        step="site_lists",
        item_count=len(items),
        output_path=str(output_path),
        meta={"mode": "mock", "api_url": api_url},
    )
