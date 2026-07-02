from __future__ import annotations

from datetime import datetime, timezone
from time import struct_time
from urllib.parse import urlencode

import feedparser

from modnews_pipeline.config import PaperAttachConfig
from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import PaperItem, StepResult

ARXIV_API_URL = "https://export.arxiv.org/api/query"


def fetch_arxiv_papers(ctx: PipelineContext, config: PaperAttachConfig) -> tuple[list[PaperItem], StepResult]:
    params = {
        "search_query": config.query,
        "start": 0,
        "max_results": max(1, config.limit),
        "sortBy": config.sort_by,
        "sortOrder": config.sort_order,
    }
    api_url = f"{ARXIV_API_URL}?{urlencode(params)}"
    errors: list[str] = []
    papers: list[PaperItem] = []
    try:
        response = ctx.session.get(api_url, timeout=30)
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        for entry in parsed.entries[: config.limit]:
            papers.append(_paper_from_entry(entry, ctx.scrape_date))
    except Exception as exc:
        errors.append(f"arxiv: {exc}")

    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(
        _to_json([paper.to_dict() for paper in papers]),
        encoding="utf-8",
    )
    ctx.artifacts["arxiv_papers"] = config.output_path
    return papers, StepResult(
        step="arxiv_papers",
        item_count=len(papers),
        output_path=str(config.output_path),
        errors=errors,
        meta={"api_url": api_url, "query": config.query, "limit": config.limit},
    )


def _paper_from_entry(entry, scrape_date: str) -> PaperItem:
    authors = [author.get("name", "").strip() for author in entry.get("authors", []) if author.get("name")]
    tags = entry.get("tags", [])
    categories = [tag.get("term", "").strip() for tag in tags if tag.get("term")]
    primary = None
    if entry.get("arxiv_primary_category"):
        primary = entry.arxiv_primary_category.get("term")
    link = _abs_link(entry)
    return PaperItem(
        platform="arxiv",
        title=" ".join((entry.get("title") or "").split()),
        url=link,
        pubtime=_to_iso(entry.get("published_parsed") or entry.get("updated_parsed")),
        scrape_date=scrape_date,
        summary=" ".join((entry.get("summary") or "").split()) or None,
        authors=authors,
        categories=categories,
        primary_category=primary,
        paper_id=_paper_id(link),
    )


def _abs_link(entry) -> str:
    for link in entry.get("links", []):
        if link.get("rel") == "alternate" and link.get("href"):
            return link["href"]
    return entry.get("link", "")


def _paper_id(url: str) -> str | None:
    if not url:
        return None
    return url.rstrip("/").rsplit("/", 1)[-1] or None


def _to_iso(value: struct_time | None) -> str | None:
    if not value:
        return None
    return datetime(*value[:6], tzinfo=timezone.utc).isoformat()


def _to_json(rows: list[dict]) -> str:
    import json

    return json.dumps(rows, ensure_ascii=False, indent=2)
