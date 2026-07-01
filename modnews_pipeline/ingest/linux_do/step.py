from __future__ import annotations

import json

from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import NewsItem, StepResult

from ..base import IngestStep
from .client import fetch_category_topics


class LinuxDoStep(IngestStep):
    step_name = "linux_do"

    def run(self, ctx: PipelineContext) -> tuple[list[NewsItem], StepResult]:
        mock_url = ctx.config.linux_do_api_url
        if mock_url:
            return _run_via_mock(ctx, mock_url)

        errors: list[str] = []
        items: list[NewsItem] = []

        try:
            proxy_url = self.options.get("proxy_url", ctx.config.proxy_url)
            topics = fetch_category_topics(proxy_url=proxy_url)
            limit = int(self.options.get("limit", 30))
            skip_pinned = bool(self.options.get("skip_pinned", False))
            for topic in topics[:limit]:
                if skip_pinned and topic.title.startswith("关于"):
                    continue
                items.append(
                    NewsItem(
                        platform="linux_do",
                        title=topic.title,
                        url=topic.url,
                        pubtime=topic.created_at,
                        scrape_date=ctx.scrape_date,
                    )
                )
        except Exception as exc:
            errors.append(str(exc))

        output_path = ctx.work_dir / "linux_do_items.json"
        output_path.write_text(
            json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        ctx.artifacts[self.step_name] = output_path
        return items, StepResult(
            step=self.step_name,
            item_count=len(items),
            output_path=str(output_path),
            errors=errors,
        )


def _run_via_mock(ctx: PipelineContext, api_url: str) -> tuple[list[NewsItem], StepResult]:
    resp = ctx.session.get(api_url, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    items = [
        NewsItem(
            platform=(row.get("platform") or "").strip() or "linux_do",
            title=(row.get("title") or "").strip(),
            url=row.get("url", ""),
            pubtime=row.get("pubtime"),
            scrape_date=row.get("scrape_date") or ctx.scrape_date,
        )
        for row in payload.get("items", [])
    ]
    output_path = ctx.work_dir / "linux_do_items.json"
    output_path.write_text(
        json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ctx.artifacts["linux_do"] = output_path
    return items, StepResult(
        step="linux_do",
        item_count=len(items),
        output_path=str(output_path),
        meta={"mode": "mock", "api_url": api_url},
    )
