from __future__ import annotations

import json

from .classify import run_classification
from .config import PipelineConfig, load_config
from .context import PipelineContext
from .ingest import run_ingest
from .models import EventRecord, NewsItem, PipelineResult
from .papers import attach_papers_to_events
from .progress import emit


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    ctx = PipelineContext.create(config)
    ctx.work_dir.mkdir(parents=True, exist_ok=True)

    emit("step_start", step="ingest", stage="pipeline")
    all_items, ingest_results = run_ingest(ctx, config.ingest_steps)
    emit("step_done", step="ingest", stage="pipeline", item_count=len(all_items))

    emit("step_start", step="classification", stage="pipeline", item_count=len(all_items))
    classified_items, events, classify_result = run_classification(ctx, all_items, config.classification)
    emit("step_done", step="classification", stage="pipeline", item_count=len(classified_items), event_count=len(events))

    emit("step_start", step="paper_attach", stage="pipeline", event_count=len(events))
    classified_items, events, papers, paper_result = attach_papers_to_events(
        ctx,
        classified_items,
        events,
        config.classification,
        config.paper_attach,
    )
    emit(
        "step_done",
        step="paper_attach",
        stage="pipeline",
        item_count=len(classified_items),
        event_count=len(events),
        paper_count=len(papers),
    )
    _write_classification_outputs(config, classified_items, events)

    output = PipelineResult(
        scrape_date=ctx.scrape_date,
        items=classified_items,
        events=events,
        steps=[*ingest_results, classify_result, paper_result],
        output_path=config.output_path,
        papers=papers,
    )
    config.output_path.write_text(
        json.dumps(output.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


def run_pipeline_from_path(config_path: str | None = None) -> PipelineResult:
    return run_pipeline(load_config(config_path))


def _write_classification_outputs(config: PipelineConfig, items: list[NewsItem], events: list[EventRecord]) -> None:
    config.classification.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.classification.events_output_path.parent.mkdir(parents=True, exist_ok=True)
    config.classification.output_path.write_text(
        json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    config.classification.events_output_path.write_text(
        json.dumps([event.to_dict() for event in events], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
