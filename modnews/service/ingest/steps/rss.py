from __future__ import annotations

import json
from datetime import datetime, timezone
from time import struct_time

import feedparser
import requests

from modnews.core.context import PipelineContext
from modnews.core.models import NewsItem, StepResult
from modnews.repository.source_config import source_config_store

from modnews.service.ingest.base import IngestStep


class RssStep(IngestStep):
    step_name = "rss"

    def run(self, ctx: PipelineContext) -> tuple[list[NewsItem], StepResult]:
        mock_url = ctx.config.rss_api_url
        if mock_url:
            return _run_via_mock(ctx, mock_url)

        store = source_config_store(ctx.config.project_root)
        feeds = store.enabled_rss_sources()
        limit_per_feed = int(store.load()["steps"]["rss"].get("limit_per_feed", 20))
        items: list[NewsItem] = []
        errors: list[str] = []

        for feed in feeds:
            if feed.get("enabled", True) is False:
                continue
            url = feed["url"]
            try:
                resp = ctx.session.get(url, timeout=20)
                resp.raise_for_status()
                parsed = feedparser.parse(resp.content)
                for entry in parsed.entries[: self.options.get("limit_per_feed", limit_per_feed)]:
                    items.append(
                        NewsItem(
                            platform=feed["id"],
                            title=(entry.get("title") or "").strip(),
                            url=entry.get("link", ""),
                            pubtime=_to_iso(entry.get("published_parsed") or entry.get("updated_parsed")),
                            scrape_date=ctx.scrape_date,
                        )
                    )
            except Exception as exc:
                errors.append(f"{feed['id']}: {exc}")

        output_path = ctx.work_dir / "rss_items.json"
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


def _to_iso(value: struct_time | None) -> str | None:
    if not value:
        return None
    return datetime(*value[:6], tzinfo=timezone.utc).isoformat()


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
    output_path = ctx.work_dir / "rss_items.json"
    output_path.write_text(
        json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ctx.artifacts["rss"] = output_path
    return items, StepResult(
        step="rss",
        item_count=len(items),
        output_path=str(output_path),
        meta={"mode": "mock", "api_url": api_url},
    )
