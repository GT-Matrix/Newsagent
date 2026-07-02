from __future__ import annotations

import json

from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import NewsItem, StepResult
from modnews_pipeline.web_extraction import WebExtractionOrchestrator

from ..base import IngestStep

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
)


class SiteListsStep(IngestStep):
    step_name = "site_lists"

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
