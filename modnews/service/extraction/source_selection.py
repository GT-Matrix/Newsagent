from __future__ import annotations

import json
from pathlib import Path

from modnews.core.models import NewsItem

from .web_contract import WebSource


def enabled_sources(config: dict, requested_sites: list[str] | None = None) -> list[WebSource]:
    raw_sources = config.get("sources", {}).get("site_lists", {})
    requested = set(requested_sites or [])
    sources: list[WebSource] = []
    for source_id, raw in raw_sources.items():
        if not isinstance(raw, dict):
            continue
        if requested and source_id not in requested:
            continue
        source = WebSource.from_config(source_id, raw)
        if source.enabled:
            sources.append(source)
    return sources


def load_job_items(output_path: str | None, *, default_scrape_date: str, source_id: str) -> list[NewsItem]:
    if not output_path:
        return []
    try:
        rows = json.loads(Path(output_path).read_text(encoding="utf-8"))
    except Exception:
        rows = []
    items: list[NewsItem] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        items.append(
            NewsItem(
                platform=str(row.get("platform") or source_id),
                title=str(row.get("title") or ""),
                url=str(row.get("url") or ""),
                pubtime=row.get("pubtime"),
                scrape_date=str(row.get("scrape_date") or default_scrape_date),
            )
        )
    return items
