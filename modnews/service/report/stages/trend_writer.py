from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import requests

from modnews.core.config import LlmConfig
from modnews.core.progress import emit
from modnews.service.classify.llm_client import LlmClient
from modnews.service.report.models import EnrichedEvent

MAX_SELECTED_SNIPPET_CHARS = 900
MAX_ALL_TITLE_CHARS = 140


def generate_trend_summary(
    events: list[EnrichedEvent],
    evidence_payload: list[dict[str, Any]],
    llm_config: LlmConfig | None,
    session: requests.Session | None = None,
) -> str | None:
    if llm_config is None or not llm_config.base_url or not llm_config.api_key:
        return None

    selected = [event for event in events if event.should_include_report and event.report_section != "watchlist"]
    if not selected:
        return None

    client = LlmClient(_trend_llm_config(llm_config), session or requests.Session())
    evidence_by_id = {str(row.get("event_id")): row for row in evidence_payload}
    payload = _build_payload(events, selected, evidence_by_id)
    emit("trend_summary_start", step="trend_summary", selected_count=len(selected), event_count=len(events))
    try:
        result = client.complete_json(
            task="daily_trend_summary",
            messages=[
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
            ],
        )
        summary = _clean_summary(result.get("trend_summary"))
        if summary:
            emit("trend_summary_done", step="trend_summary", status="done")
            return summary
    except Exception as exc:
        emit("trend_summary_error", step="trend_summary", error=f"{type(exc).__name__}: {exc}")
    return None


def _trend_llm_config(config: LlmConfig) -> LlmConfig:
    return replace(
        config,
        temperature=0.35,
        timeout_seconds=min(max(config.timeout_seconds, 75), 120),
        max_retries=min(max(config.max_retries, 2), 3),
    )


def _system_prompt() -> str:
    return (
        "You are Newsagent's senior Chinese AI industry editor. "
        "Write a one-paragraph trend observation for an internal AI morning briefing. "
        "Use the selected report items as the core signal, and use the full event title list as broader market context. "
        "Do not simply count categories. Do not use bullets. Do not invent facts not supported by the input. "
        "Do not mention backend scoring, verification, source fetching, JSON, or the phrase 'selected items'. "
        "Return strict JSON with exactly one field: trend_summary. "
        "trend_summary must be Chinese, one paragraph, 180-320 Chinese characters, with concrete synthesis and editorial judgment."
    )


def _build_payload(
    events: list[EnrichedEvent],
    selected: list[EnrichedEvent],
    evidence_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selected_payload = []
    for event in selected:
        evidence = evidence_by_id.get(event.event_id, {})
        selected_payload.append(
            {
                "section": event.report_section,
                "title": event.title,
                "brief": event.one_sentence,
                "why_important": event.why_important,
                "type": event.normalized_event_type,
                "score": round(event.final_score, 1),
                "platforms": event.platforms[:6],
                "source_titles": [str(source.get("title") or "") for source in event.source_items[:5]],
                "source_snippets": _source_snippets(evidence),
            }
        )

    all_title_payload = []
    for event in events:
        if event.verify_status == "needs_review":
            continue
        all_title_payload.append(
            {
                "title": _truncate(event.title, MAX_ALL_TITLE_CHARS),
                "type": event.normalized_event_type,
                "layer": event.content_layer,
                "score": round(event.final_score, 1),
                "platforms": event.platforms[:4],
            }
        )

    return {
        "task": "Generate one broader daily trend observation.",
        "selected_report_items_core_signal": selected_payload,
        "all_events_title_level_context": all_title_payload,
        "editorial_requirements": [
            "Use selected items for factual anchors.",
            "Use all event titles to infer broader context and repeated signals.",
            "Avoid mechanical category counting.",
            "Write as a Newsagent editorial synthesis, not a data report.",
        ],
    }


def _source_snippets(evidence: dict[str, Any]) -> list[dict[str, str]]:
    snippets = []
    for item in (evidence.get("evidence_items") or [])[:2]:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        snippets.append(
            {
                "platform": str(item.get("platform") or ""),
                "title": str(item.get("title") or ""),
                "text": _truncate(text, MAX_SELECTED_SNIPPET_CHARS),
            }
        )
    return snippets


def _clean_summary(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.strip().split())
    text = text.lstrip("- ").strip()
    text = text.replace("\ufffd", "").rstrip(" ?？")
    if not text:
        return ""
    if not text.endswith(("。", "！", "？", ".", "!", "?")):
        text += "。"
    return text[:520].rstrip(" ?？")


def _truncate(value: str, max_chars: int) -> str:
    value = " ".join(str(value or "").split())
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"
