from __future__ import annotations

from modnews_pipeline.config import StepConfig
from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import NewsItem, StepResult
from modnews_pipeline.progress import emit
from modnews.service.ingest.registry import STEP_FACTORIES, default_ingest_registry


def run_ingest(ctx: PipelineContext, steps: list[StepConfig]) -> tuple[list[NewsItem], list[StepResult]]:
    all_items: list[NewsItem] = []
    results: list[StepResult] = []
    registry = default_ingest_registry()

    for step_config in steps:
        if not step_config.enabled:
            continue
        step_cls = registry.get(step_config.type)
        step = step_cls(**step_config.options)
        emit("ingest_source_start", source=step_config.type)
        items, result = step.run(ctx)
        emit("ingest_source_done", source=step_config.type, item_count=len(items), errors=result.errors)
        all_items.extend(items)
        results.append(result)

    return all_items, results
