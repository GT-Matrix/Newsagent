from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from modnews_pipeline.config import PaperAttachConfig
from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import PaperItem, StepResult

SOURCE_ID = "huggingface_papers_trending"
DEFAULT_URL = "https://huggingface.co/papers/trending"


def fetch_huggingface_papers(ctx: PipelineContext, config: PaperAttachConfig) -> tuple[list[PaperItem], StepResult]:
    errors: list[str] = []
    papers: list[PaperItem] = []
    diagnostics: dict[str, Any] = {}
    extractor_path = _extractor_path(ctx)
    try:
        module = _load_extractor(extractor_path)
        result = module.run(
            {
                "source_id": SOURCE_ID,
                "url": config.huggingface_url or DEFAULT_URL,
                "scrape_date": ctx.scrape_date,
                "limit": max(1, config.huggingface_limit or config.limit),
                "options": {},
            }
        )
        diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}
        if not result.get("ok"):
            errors.append(f"{SOURCE_ID}: {result.get('status') or 'failed'}: {diagnostics.get('message') or ''}".strip())
        for row in result.get("items", []):
            if isinstance(row, dict):
                paper = _paper_from_row(row, ctx.scrape_date)
                if paper:
                    papers.append(paper)
    except Exception as exc:
        errors.append(f"{SOURCE_ID}: {type(exc).__name__}: {exc}")

    output_path = config.output_path.parent / "huggingface_papers.json"
    output_path.write_text(json.dumps([paper.to_dict() for paper in papers], ensure_ascii=False, indent=2), encoding="utf-8")
    ctx.artifacts["huggingface_papers"] = output_path
    return papers, StepResult(
        step="huggingface_papers",
        item_count=len(papers),
        output_path=str(output_path),
        errors=errors,
        meta={"source": SOURCE_ID, "diagnostics": diagnostics},
    )


def _extractor_path(ctx: PipelineContext) -> Path:
    project_root = ctx.config.output_path.parent.parent
    return project_root / "extractors" / SOURCE_ID / "current" / "extractor.py"


def _load_extractor(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)
    spec = importlib.util.spec_from_file_location("huggingface_papers_trending_extractor", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load extractor from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _paper_from_row(row: dict[str, Any], scrape_date: str) -> PaperItem | None:
    title = str(row.get("title") or "").strip()
    url = str(row.get("url") or "").strip()
    if not title or not url:
        return None
    return PaperItem(
        platform=str(row.get("platform") or SOURCE_ID),
        title=" ".join(title.split()),
        url=url,
        pubtime=_optional_str(row.get("pubtime") or row.get("published_at") or row.get("publishedAt")),
        scrape_date=str(row.get("scrape_date") or scrape_date),
        summary=_optional_str(row.get("summary")),
        authors=_str_list(row.get("authors")),
        categories=_str_list(row.get("categories")),
        primary_category=_optional_str(row.get("primary_category")),
        paper_id=_optional_str(row.get("paper_id") or row.get("external_id")),
    )


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item not in (None, "")]
