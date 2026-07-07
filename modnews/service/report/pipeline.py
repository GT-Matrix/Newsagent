from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from modnews.service.report.editor import polish_report_events
from modnews.service.report.evidence import enrich_report_evidence
from modnews.service.report.io.event_loader import load_processed_candidates
from modnews.service.report.io.report_writer import write_enriched_events, write_json, write_text
from modnews.service.report.models import EnrichedEvent
from modnews.service.report.reporter import (
    assign_report_sections,
    build_debug_report_markdown,
    build_report_markdown,
    report_candidates_payload,
    review_candidates_payload,
)
from modnews.service.report.stages.classifier import classify_event
from modnews.service.report.stages.scorer import score_event
from modnews.service.report.stages.summarizer import summarize_event
from modnews.service.report.stages.trend_writer import generate_trend_summary
from modnews.service.report.stages.verifier import verify_event
from modnews.service.report.utils.text import text_quality


@dataclass(slots=True)
class ReportDraft:
    report_date: date
    enriched_events: list[EnrichedEvent]
    evidence_payload: list[dict[str, object]]


def run_pipeline(
    input_path: Path,
    output_dir: Path,
    report_date: date,
    config_path: Path | None = None,
) -> list[EnrichedEvent]:
    draft = build_report_draft(input_path, report_date)
    enriched = draft.enriched_events
    evidence_payload = draft.evidence_payload

    trend_summary: str | None = None
    if config_path is not None:
        from modnews.core.config import load_config
        from modnews.core.context import PipelineContext

        modnews_config = load_config(str(config_path))
        ctx = PipelineContext.create(modnews_config)
        polish_report_events(enriched, evidence_payload, modnews_config.classification.llm, ctx.session)
        trend_summary = generate_trend_summary(enriched, evidence_payload, modnews_config.classification.llm, ctx.session)

    write_report_outputs(output_dir, enriched, evidence_payload, report_date, trend_summary)
    return enriched


def build_report_draft(input_path: Path, report_date: date) -> ReportDraft:
    candidates = load_processed_candidates(input_path)
    enriched: list[EnrichedEvent] = []

    for candidate in candidates:
        content_layer, normalized_type = classify_event(candidate)
        score = score_event(candidate, normalized_type, report_date)
        title, one_sentence, why_important = summarize_event(candidate, normalized_type)
        quality = text_quality(title, one_sentence, candidate.event_type, " ".join(candidate.key_entities))
        verify_status, verify_reason = verify_event(candidate, quality)
        warnings = list(candidate.original.get("_validation_warnings", []))
        if candidate.latest_pubtime is None:
            warnings.append("latest_pubtime_missing")
        if quality != "ok":
            warnings.append(f"text_quality_{quality}")
        if not candidate.source_items:
            warnings.append("source_items_missing")

        enriched.append(
            EnrichedEvent(
                event_id=candidate.event_id,
                title=title,
                one_sentence=one_sentence,
                why_important=why_important,
                content_layer=content_layer,
                topic=normalized_type,
                normalized_event_type=normalized_type,
                entities=candidate.key_entities,
                platforms=candidate.platforms,
                member_count=candidate.member_count,
                source_news_ids=candidate.source_news_ids,
                source_items=[asdict(source) for source in candidate.source_items],
                latest_pubtime=candidate.latest_pubtime.isoformat() if candidate.latest_pubtime else None,
                confidence=candidate.confidence,
                importance_score=score.importance_score,
                source_score=score.source_score,
                freshness_score=score.freshness_score,
                relevance_score=score.relevance_score,
                actionability_score=score.actionability_score,
                novelty_score=score.novelty_score,
                risk_penalty=score.risk_penalty,
                final_score=score.final_score,
                score_reason=score.score_reason,
                verify_status=verify_status,
                verify_reason=verify_reason,
                text_quality=quality,
                warnings=warnings,
                original_event=candidate.original,
            )
        )

    enriched.sort(key=lambda event: (event.final_score, event.importance_score, event.source_score), reverse=True)
    assign_report_sections(enriched)
    evidence_payload = enrich_report_evidence(enriched)
    return ReportDraft(
        report_date=report_date,
        enriched_events=enriched,
        evidence_payload=evidence_payload,
    )


def write_report_outputs(
    output_dir: Path,
    enriched: list[EnrichedEvent],
    evidence_payload: list[dict[str, object]],
    report_date: date,
    trend_summary: str | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_enriched_events(output_dir / "enriched_events.json", enriched)
    write_json(output_dir / "evidence_events.json", evidence_payload)
    write_json(output_dir / "report_candidates.json", report_candidates_payload(enriched))
    write_json(output_dir / "review_candidates.json", review_candidates_payload(enriched))
    write_json(output_dir / "trend_summary.json", {"trend_summary": trend_summary, "mode": "llm" if trend_summary else "fallback"})
    write_text(output_dir / "daily_report.md", build_report_markdown(enriched, report_date, trend_summary))
    write_text(output_dir / "daily_report_debug.md", build_debug_report_markdown(enriched, report_date, trend_summary))
