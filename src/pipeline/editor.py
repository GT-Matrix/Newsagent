from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

import requests

from modnews_pipeline.classify.llm_client import LlmClient
from modnews_pipeline.config import LlmConfig
from modnews_pipeline.progress import emit
from src.models import EnrichedEvent

MAX_EVIDENCE_CHARS = 4200
BACKGROUND_PATTERNS = [
    r"[^。！？.!?]*(?:原文回溯|系统已读取|证据强度|直接依据|原始来源|目前暂未抓取到可用原文|仍以已聚类标题判断)[^。！？.!?]*[。！？.!?]",
    r"[^。！？.!?]*证据(?:强度|来自|来源)[^。！？.!?]*[。！？.!?]",
    r"[^。！？.!?]*(?:页面|内容)(?:未完全加载|不可读|抓取失败)[^。！？.!?]*[。！？.!?]",
    r"[^。！？.!?]*仍需(?:进一步)?核验[^。！？.!?]*[。！？.!?]",
    r"[^。！？.!?]*单一(?:来源|媒体报道)[^。！？.!?]*[。！？.!?]",
    r"[^。！？.!?]*后续可结合(?:论文|基准结果)?继续跟进[^。！？.!?]*[。！？.!?]",
]


def polish_report_events(
    events: list[EnrichedEvent],
    evidence_payload: list[dict[str, Any]],
    llm_config: LlmConfig | None,
    session: requests.Session | None = None,
) -> None:
    if llm_config is None or not llm_config.base_url or not llm_config.api_key:
        return

    selected = [event for event in events if event.should_include_report]
    evidence_by_id = {str(row.get("event_id")): row for row in evidence_payload}
    client = LlmClient(_editor_llm_config(llm_config), session or requests.Session())

    for index, event in enumerate(selected, start=1):
        evidence = evidence_by_id.get(event.event_id, {})
        emit("report_polish_start", step="report_polish", item=index, total=len(selected), title=event.title)
        try:
            result = client.complete_json(
                task="final_report_polish",
                messages=[
                    {"role": "system", "content": _system_prompt()},
                    {"role": "user", "content": _user_prompt(event, evidence)},
                ],
            )
            _apply_polish(event, result)
            event.evidence_summary["llm_polished"] = True
            emit("report_polish_done", step="report_polish", item=index, total=len(selected), title=event.title)
        except Exception as exc:
            event.warnings.append(f"report_polish_failed:{type(exc).__name__}")
            event.evidence_summary["llm_polished"] = False
            event.evidence_summary["polish_error"] = f"{type(exc).__name__}: {exc}"
            emit("report_polish_error", step="report_polish", item=index, total=len(selected), error=str(exc))


def sanitize_public_report_events(events: list[EnrichedEvent]) -> None:
    for event in events:
        if not event.should_include_report:
            continue
        raw_brief = event.one_sentence
        raw_why = event.why_important
        brief = _clean_public_text(raw_brief, max_len=420)
        why = _clean_public_text(event.why_important, max_len=200)
        if _has_background_text(raw_brief):
            event.one_sentence = _fallback_public_brief(event)
        elif brief:
            event.one_sentence = brief
        if why:
            event.why_important = why
        elif _has_background_text(raw_why):
            event.why_important = "这条线索值得继续观察其后续进展和外部验证。"


def _editor_llm_config(config: LlmConfig) -> LlmConfig:
    return replace(
        config,
        temperature=0.2,
        timeout_seconds=min(max(config.timeout_seconds, 60), 90),
        max_retries=min(max(config.max_retries, 2), 3),
    )


def _system_prompt() -> str:
    return (
        "You are an editor for a Chinese AI industry morning briefing. "
        "Use only the provided event metadata and source snippets. Do not invent facts, numbers, dates, entities, or source claims. "
        "Return a strict JSON object with exactly these fields: title, brief, why_important. "
        "Write title, brief, and why_important in Chinese. Keep necessary English product/company names. "
        "Title should be readable, specific, and about 12-32 Chinese characters when possible. "
        "Brief should be 2-3 Chinese sentences for readers: what happened, key details, and concrete context. "
        "Do NOT mention backend verification process, evidence strength, fetched source count, unreadable pages, failed fetches, 'single source', or 'needs verification' in the public brief. "
        "Those verification notes are stored separately in debug files. "
        "why_important should be one Chinese sentence explaining practical impact on AI products, models, compute, research, policy, or business."
    )


def _user_prompt(event: EnrichedEvent, evidence: dict[str, Any]) -> str:
    evidence_summary = evidence.get("evidence_summary") or event.evidence_summary or {}
    evidence_items = evidence.get("evidence_items") or []
    snippets = []
    for item in evidence_items[:2]:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        snippets.append(
            {
                "platform": item.get("platform"),
                "domain": item.get("canonical_domain"),
                "url": item.get("url"),
                "title": item.get("title"),
                "text": text[:MAX_EVIDENCE_CHARS],
            }
        )
    payload = {
        "current_title": event.title,
        "current_brief": event.one_sentence,
        "current_why_important": event.why_important,
        "event_type": event.normalized_event_type,
        "report_section": event.report_section,
        "verify_status_for_internal_use_only": event.verify_status,
        "score": round(event.final_score, 1),
        "entities": event.entities[:8],
        "platforms": event.platforms[:8],
        "source_titles": [str(source.get("title") or "") for source in event.source_items[:6]],
        "debug_evidence_summary_do_not_quote": evidence_summary,
        "source_snippets": snippets,
    }
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)


def _apply_polish(event: EnrichedEvent, result: dict[str, Any]) -> None:
    title = _clean_text(result.get("title"), max_len=80)
    brief = _clean_public_text(result.get("brief"), max_len=420)
    why = _clean_public_text(result.get("why_important"), max_len=200)
    if title:
        event.title = title
    if brief:
        event.one_sentence = brief
    if why:
        event.why_important = why


def _clean_text(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.strip().split())
    if not text:
        return ""
    return text[:max_len].rstrip()


def _clean_public_text(value: Any, max_len: int) -> str:
    text = _clean_text(value, max_len=max_len * 2)
    for pattern in BACKGROUND_PATTERNS:
        text = re.sub(pattern, "", text)
    text = " ".join(text.split()).strip(" ，,。")
    if text and not text.endswith(("。", "！", "？", ".", "!", "?")):
        text += "。"
    return text[:max_len].rstrip()


def _has_background_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return any(re.search(pattern, value) for pattern in BACKGROUND_PATTERNS)


def _fallback_public_brief(event: EnrichedEvent) -> str:
    title = _clean_text(event.title, max_len=120).rstrip("。.!?！？")
    if not title:
        title = "这条 AI 行业线索"
    if event.report_section == "watchlist":
        return f"{title}。目前更适合作为待观察线索，后续需要结合更多来源确认影响。"
    return f"{title}。该事件值得关注，后续可继续跟踪其对产品、模型、基础设施或行业竞争的影响。"
