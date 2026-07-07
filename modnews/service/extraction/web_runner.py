from __future__ import annotations

from typing import Any

from modnews.service.extraction.contract import ExtractorRunInput, ExtractorRunResult
from modnews.service.extraction.registry import ExtractorRegistry
from modnews.service.extraction.repair_policy import classify_result
from modnews.service.extraction.web_contract import WebSource


def run_extractor(
    *,
    registry: ExtractorRegistry,
    source: WebSource,
    scrape_date: str,
    limit: int,
) -> tuple[ExtractorRunResult, dict[str, Any]]:
    if not source.extractor_id:
        raise RuntimeError(f"web source {source.id} has no extractor_id")
    payload = ExtractorRunInput(
        source_id=source.id,
        url=source.url,
        scrape_date=scrape_date,
        limit=limit,
        options={
            **source.options,
            "content_type": source.content_type,
            "tags": source.tags,
        },
    )
    result = registry.run(source.extractor_id, payload)
    raw = result.to_dict()
    failure = classify_result(raw)
    if failure:
        raise RuntimeError(f"{failure.error_type}: {failure.message}")
    return result, raw
