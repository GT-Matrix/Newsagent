from __future__ import annotations

import json

from modnews_pipeline.classify.events import assign_item_to_event
from modnews_pipeline.classify.llm_client import LlmClient
from modnews_pipeline.classify.types import EventState
from modnews_pipeline.classify.utils import clean_event_type, clean_list, clean_string, event_payload, normalize_confidence, prepare_item
from modnews_pipeline.config import ClassificationConfig, PaperAttachConfig
from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import EventRecord, NewsItem, PaperItem, StepResult
from modnews_pipeline.progress import emit

from .arxiv import fetch_arxiv_papers


def attach_papers_to_events(
    ctx: PipelineContext,
    items: list[NewsItem],
    events: list[EventRecord],
    classification_config: ClassificationConfig,
    config: PaperAttachConfig,
) -> tuple[list[NewsItem], list[EventRecord], list[PaperItem], StepResult]:
    if not config.enabled:
        return items, events, [], StepResult(step="paper_attach", item_count=0, meta={"enabled": False})

    if config.source != "arxiv":
        raise ValueError(f"Unsupported paper source: {config.source}")

    papers, fetch_result = fetch_arxiv_papers(ctx, config)
    if not papers or fetch_result.errors:
        return items, events, papers, StepResult(
            step="paper_attach",
            item_count=0,
            output_path=str(config.decisions_output_path),
            errors=fetch_result.errors,
            meta={"paper_count": len(papers), "attached_count": 0, "created_event_count": 0, "skipped_count": 0},
        )

    client = LlmClient(classification_config.llm, ctx.session)
    event_states = [EventState(record=event) for event in events]
    response = _decide_paper_attach(client, papers, event_states, config)
    decisions = response.get("paper_decisions") if isinstance(response.get("paper_decisions"), list) else []
    by_index = {index: paper for index, paper in enumerate(papers)}
    attached_count = 0
    created_count = 0
    skipped_count = 0
    applied_decisions: list[dict] = []

    for row in decisions:
        paper_index = _int_or_none(row.get("paper_index"))
        if paper_index is None or paper_index not in by_index:
            continue
        paper = by_index[paper_index]
        decision = _normalize_decision(row.get("decision"))
        confidence = normalize_confidence(row.get("confidence"))
        reason = clean_string(row.get("reason"))
        news_item = _paper_to_news_item(paper, config.max_summary_chars)
        entry = prepare_item(len(items), news_item)
        news_item.classification_reason = reason
        news_item.relevance_score = 90
        news_item.event_type = clean_event_type(row.get("event_type") or "research")
        news_item.entities = clean_list(row.get("key_entities")) or paper.authors[:5]
        news_item.canonical_summary = clean_string(row.get("event_summary")) or _paper_summary(paper, config.max_summary_chars)

        if decision == "assign":
            event_id = clean_string(row.get("matched_event_id"))
            target = next((state for state in event_states if state.record.event_id == event_id), None)
            if target is None:
                decision = "create"
            else:
                items.append(news_item)
                assign_item_to_event(entry, target, confidence)
                attached_count += 1
                emit("paper_attach_decision", paper_index=paper_index, decision="assign", event_id=event_id)

        if decision == "create":
            event = EventRecord(
                event_id=_new_event_id(ctx.scrape_date, len(event_states) + 1),
                event_label=clean_string(row.get("event_label")) or paper.title,
                member_count=0,
                platforms=[],
                latest_pubtime=None,
                representative_titles=[],
                confidence=confidence,
                event_summary=clean_string(row.get("event_summary")) or _paper_summary(paper, config.max_summary_chars),
                event_type=clean_event_type(row.get("event_type") or "research"),
                key_entities=clean_list(row.get("key_entities")) or paper.authors[:5],
                source_news_ids=[],
                last_llm_updated_at=ctx.scrape_date,
            )
            state = EventState(record=event)
            event_states.append(state)
            items.append(news_item)
            assign_item_to_event(entry, state, confidence)
            attached_count += 1
            created_count += 1
            emit("paper_attach_decision", paper_index=paper_index, decision="create", event_id=event.event_id)

        if decision == "skip":
            skipped_count += 1
            emit("paper_attach_decision", paper_index=paper_index, decision="skip", reason=reason)

        applied_decisions.append({**row, "normalized_decision": decision})

    seen = {_int_or_none(row.get("paper_index")) for row in applied_decisions}
    skipped_count += len([index for index in by_index if index not in seen])
    output_payload = {
        "papers": [paper.to_dict() for paper in papers],
        "decisions": applied_decisions,
        "raw_response": response,
    }
    config.decisions_output_path.parent.mkdir(parents=True, exist_ok=True)
    config.decisions_output_path.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    ctx.artifacts["paper_attach_decisions"] = config.decisions_output_path

    return items, [state.record for state in event_states], papers, StepResult(
        step="paper_attach",
        item_count=attached_count,
        output_path=str(config.decisions_output_path),
        meta={
            "paper_count": len(papers),
            "attached_count": attached_count,
            "created_event_count": created_count,
            "skipped_count": skipped_count,
            "source_output_path": str(config.output_path),
        },
    )


def _decide_paper_attach(
    client: LlmClient,
    papers: list[PaperItem],
    events: list[EventState],
    config: PaperAttachConfig,
) -> dict:
    paper_payload = [_paper_payload(index, paper, config.max_summary_chars) for index, paper in enumerate(papers)]
    event_payloads = [event_payload(state.record) for state in events]
    emit("paper_attach_request", paper_count=len(paper_payload), event_count=len(event_payloads))
    return client.complete_json(
        task="paper_attach",
        messages=[
            {"role": "system", "content": _paper_attach_system_prompt()},
            {
                "role": "user",
                "content": json.dumps(
                    {"papers": paper_payload, "existing_events": event_payloads},
                    ensure_ascii=False,
                ),
            },
        ],
    )


def _paper_attach_system_prompt() -> str:
    return """
You attach recent AI research papers to an existing AI-news event list.
Output only valid JSON:
{"paper_decisions":[{"paper_index":0,"decision":"assign|create|skip","matched_event_id":null,"event_label":"","event_summary":"","event_type":"research","key_entities":[],"confidence":0.0,"reason":""}]}

Rules:
- Every input paper_index must appear exactly once.
- Use assign when the paper is clearly about the same concrete event, model, benchmark, release, or research result as one existing event.
- Use create only when the paper itself is notable enough to become a concrete AI research event.
- Use skip for ordinary incremental papers, weakly related papers, unclear papers, or papers that do not deserve an event today.
- Do not output discard.
- matched_event_id must be null unless decision is assign.
- For create, write concise Chinese event_label and event_summary.
- confidence must be a decimal probability from 0.0 to 1.0.
""".strip()


def _paper_payload(index: int, paper: PaperItem, max_summary_chars: int) -> dict:
    return {
        "paper_index": index,
        "title": paper.title,
        "summary": _paper_summary(paper, max_summary_chars),
        "authors": paper.authors[:8],
        "categories": paper.categories,
        "primary_category": paper.primary_category,
        "pubtime": paper.pubtime,
        "url": paper.url,
    }


def _paper_to_news_item(paper: PaperItem, max_summary_chars: int) -> NewsItem:
    return NewsItem(
        platform=paper.platform,
        title=paper.title,
        url=paper.url,
        pubtime=paper.pubtime,
        scrape_date=paper.scrape_date,
        canonical_summary=_paper_summary(paper, max_summary_chars),
        entities=paper.authors[:5],
        event_type="research",
    )


def _paper_summary(paper: PaperItem, max_chars: int) -> str | None:
    if not paper.summary:
        return None
    return paper.summary[:max(1, max_chars)]


def _normalize_decision(value) -> str:
    decision = str(value or "skip").strip().lower()
    if decision not in {"assign", "create", "skip"}:
        return "skip"
    return decision


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _new_event_id(scrape_date: str, index: int) -> str:
    date_part = scrape_date[:10].replace("-", "")
    return f"evt_{date_part}_p{index:04d}"
