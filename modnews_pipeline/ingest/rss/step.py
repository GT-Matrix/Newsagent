from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path
from time import struct_time
import time

import feedparser
import requests
from urllib3.exceptions import InsecureRequestWarning

from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import NewsItem, StepResult

from ..base import IngestStep, fetch_via_curl

RSS_USER_AGENT = "newsagent-rss/1.0"


class RssStep(IngestStep):
    step_name = "rss"

    def run(self, ctx: PipelineContext) -> tuple[list[NewsItem], StepResult]:
        mock_url = ctx.config.rss_api_url
        if mock_url:
            return _run_via_mock(ctx, mock_url)

        feeds = json.loads(ctx.config.rss_sources_path.read_text(encoding="utf-8"))
        items: list[NewsItem] = []
        errors: list[str] = []
        ssl_fallback_sources: list[str] = []
        cache_fallback_sources: list[str] = []

        for feed in feeds:
            if feed.get("enabled", True) is False:
                continue
            url = feed["url"]
            try:
                resp, used_ssl_fallback = _fetch_feed(ctx, url)
                if used_ssl_fallback:
                    ssl_fallback_sources.append(feed["id"])
                resp.raise_for_status()
                parsed = feedparser.parse(resp.content)
                for entry in parsed.entries[: self.options.get("limit_per_feed", 20)]:
                    items.append(
                        NewsItem(
                            platform=feed["id"],
                            title=(entry.get("title") or "").strip(),
                            url=entry.get("link", ""),
                            pubtime=_to_iso(entry.get("published_parsed") or entry.get("updated_parsed")),
                            scrape_date=ctx.scrape_date,
                        )
                    )
                _write_feed_cache(ctx, feed["id"], [item for item in items if item.platform == feed["id"]])
            except Exception as exc:
                cached = _read_feed_cache(ctx, feed["id"])
                if cached:
                    items.extend(cached)
                    cache_fallback_sources.append(feed["id"])
                    errors.append(f"{feed['id']}: live fetch failed, used cached items: {exc}")
                else:
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
            meta={"ssl_fallback_sources": ssl_fallback_sources, "cache_fallback_sources": cache_fallback_sources},
        )


def _to_iso(value: struct_time | None) -> str | None:
    if not value:
        return None
    return datetime(*value[:6], tzinfo=timezone.utc).isoformat()


def _fetch_feed(ctx: PipelineContext, url: str) -> tuple[requests.Response | object, bool]:
    try:
        return ctx.session.get(url, timeout=20), False
    except requests.RequestException:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InsecureRequestWarning)
            try:
                return ctx.session.get(url, timeout=20, verify=False), True
            except requests.RequestException:
                return fetch_via_curl(url, user_agent=RSS_USER_AGENT), True


def _cache_path(ctx: PipelineContext, feed_id: str) -> Path:
    return ctx.config.newsnow_cache_dir.parent / "rss" / f"{feed_id}.json"


def _write_feed_cache(ctx: PipelineContext, feed_id: str, items: list[NewsItem]) -> None:
    path = _cache_path(ctx, feed_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2), encoding="utf-8")


def _read_feed_cache(ctx: PipelineContext, feed_id: str) -> list[NewsItem]:
    path = _cache_path(ctx, feed_id)
    if not path.exists():
        return []
    if time.time() - path.stat().st_mtime > 3 * 24 * 60 * 60:
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(rows, list):
        return []
    items: list[NewsItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        items.append(
            NewsItem(
                platform=feed_id,
                title=str(row.get("title") or ""),
                url=str(row.get("url") or ""),
                pubtime=row.get("pubtime"),
                scrape_date=ctx.scrape_date,
            )
        )
    return items


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
