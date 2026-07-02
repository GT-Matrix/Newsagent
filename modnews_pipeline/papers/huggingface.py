from __future__ import annotations

import html
import json
import re

from modnews_pipeline.config import PaperAttachConfig
from modnews_pipeline.context import PipelineContext
from modnews_pipeline.extractors.contract import ExtractorRunInput
from modnews_pipeline.extractors.registry import registry_from_project
from modnews_pipeline.models import PaperItem, StepResult

HUGGINGFACE_TRENDING_URL = "https://huggingface.co/papers/trending"


def fetch_huggingface_papers(ctx: PipelineContext, config: PaperAttachConfig) -> tuple[list[PaperItem], StepResult]:
    errors: list[str] = []
    papers: list[PaperItem] = []
    try:
        managed = _fetch_managed(ctx, config)
        if managed is not None:
            papers = managed
        else:
            response = ctx.session.get(HUGGINGFACE_TRENDING_URL, timeout=30)
            response.raise_for_status()
            rows = _parse_daily_papers(response.text)
            for row in rows[: config.limit]:
                papers.append(_paper_from_row(row, ctx.scrape_date))
    except Exception as exc:
        errors.append(f"huggingface: {exc}")

    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(
        _to_json([paper.to_dict() for paper in papers]),
        encoding="utf-8",
    )
    ctx.artifacts["huggingface_papers"] = config.output_path
    return papers, StepResult(
        step="huggingface_papers",
        item_count=len(papers),
        output_path=str(config.output_path),
        errors=errors,
        meta={"api_url": HUGGINGFACE_TRENDING_URL, "limit": config.limit},
    )


def _fetch_managed(ctx: PipelineContext, config: PaperAttachConfig) -> list[PaperItem] | None:
    try:
        registry = registry_from_project(ctx.config.project_root)
        result = registry.run(
            "huggingface",
            ExtractorRunInput(
                source_id="huggingface",
                url=HUGGINGFACE_TRENDING_URL,
                scrape_date=ctx.scrape_date,
                limit=max(1, config.limit),
            ),
        )
        return [
            PaperItem(
                platform=item.platform,
                title=item.title,
                url=item.url,
                pubtime=item.pubtime,
                scrape_date=item.scrape_date,
                summary=item.summary,
                authors=item.authors,
                categories=item.categories,
                primary_category=item.primary_category,
                paper_id=item.paper_id,
            )
            for item in result.items[: config.limit]
        ]
    except Exception:
        return None


def _parse_daily_papers(document: str) -> list[dict]:
    match = re.search(r'data-target="DailyPapers" data-props="([\s\S]*?)"><section', document)
    if not match:
        raise ValueError("DailyPapers payload not found")
    payload = json.loads(html.unescape(match.group(1)))
    rows = payload.get("dailyPapers")
    if not isinstance(rows, list):
        raise ValueError("dailyPapers payload is not a list")
    return rows


def _paper_from_row(row: dict, scrape_date: str) -> PaperItem:
    paper = row.get("paper") if isinstance(row.get("paper"), dict) else {}
    authors = _author_names(paper.get("authors"))
    categories = _categories(paper.get("ai_keywords"))
    paper_id = _clean(paper.get("id"))
    return PaperItem(
        platform="huggingface",
        title=_clean(row.get("title")) or _clean(paper.get("title")) or "",
        url=f"https://huggingface.co/papers/{paper_id}" if paper_id else HUGGINGFACE_TRENDING_URL,
        pubtime=_clean(row.get("publishedAt")) or _clean(paper.get("publishedAt")),
        scrape_date=scrape_date,
        summary=_clean(paper.get("ai_summary")) or _clean(row.get("summary")) or _clean(paper.get("summary")),
        authors=authors,
        categories=categories,
        primary_category=categories[0] if categories else None,
        paper_id=paper_id,
    )


def _author_names(value) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        name = _clean(row.get("name"))
        if name:
            names.append(name)
    return names


def _categories(value) -> list[str]:
    if not isinstance(value, list):
        return []
    categories: list[str] = []
    for item in value:
        name = _clean(item)
        if name:
            categories.append(name)
    return categories


def _clean(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    return text or None


def _to_json(rows: list[dict]) -> str:
    return json.dumps(rows, ensure_ascii=False, indent=2)
