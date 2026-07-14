from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import replace
from typing import Any

import requests

from modnews_pipeline.classify.llm_client import LlmClient
from modnews_pipeline.config import LlmConfig
from modnews_pipeline.progress import emit
from src.models import EnrichedEvent

MAX_TITLE_CHARS = 120
MAX_BRIEF_CHARS = 180
MAX_BUCKET_ITEMS = 8

LAYER_LABELS = {
    "news": "新闻动态与产品落地",
    "insight": "研究论文与方法评测",
    "deep_asset": "长期方法与资源沉淀",
}

SECTION_LABELS = {
    "top_news": "今日重点新闻",
    "insight": "研究论文与评测",
    "deep_asset": "长期方法与资源沉淀",
    "watchlist": "待观察线索",
}


def generate_trend_summary(
    events: list[EnrichedEvent],
    evidence_payload: list[dict[str, Any]],
    llm_config: LlmConfig | None,
    session: requests.Session | None = None,
) -> str | None:
    if llm_config is None or not llm_config.base_url or not llm_config.api_key:
        return None

    eligible = _eligible_events(events)
    if not eligible:
        return None

    client = LlmClient(_trend_llm_config(llm_config), session or requests.Session())
    payload = _build_payload(eligible)
    emit("trend_summary_start", step="trend_summary", event_count=len(events), eligible_count=len(eligible))
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


def _eligible_events(events: list[EnrichedEvent]) -> list[EnrichedEvent]:
    eligible = []
    seen_titles: set[str] = set()
    for event in events:
        title = " ".join(str(event.title or "").split())
        if not title or title in seen_titles:
            continue
        if event.verify_status in {"needs_review", "rumor"}:
            continue
        if event.content_layer == "noise":
            continue
        if event.text_quality == "low":
            continue
        if "low_news_value" in event.score_reason:
            continue
        seen_titles.add(title)
        eligible.append(event)
    return eligible


def _trend_llm_config(config: LlmConfig) -> LlmConfig:
    return replace(
        config,
        temperature=0.35,
        timeout_seconds=min(max(config.timeout_seconds, 75), 120),
        max_retries=min(max(config.max_retries, 2), 3),
    )


def _system_prompt() -> str:
    return (
        "You are NewsAgent's senior Chinese AI industry editor. "
        "Write the final '今日趋势观察' for an internal AI morning briefing. "
        "Base your judgment on the full post-filtered, evidence-checked candidate pool supplied by the user, not only the final report selection list. "
        "Do not summarize individual news items. Do not name isolated articles, rankings, launches, papers, or one-off company events. "
        "Synthesize broad industry direction from repeated signals across categories, entities, layers, and source platforms. "
        "Focus on what is changing in the market: deployment, infrastructure, model capability, agents, AI for science, safety, open source, regulation, and enterprise adoption. "
        "Write one concise Chinese paragraph with editorial judgment, not bullets and not a data report. "
        "Do not mention backend scoring, filtering, clustering, JSON, or the phrase 'event pool'. "
        "Return strict JSON with exactly one field: trend_summary. "
        "trend_summary must be Chinese, 160-260 Chinese characters, concrete and strictly supported by repeated signals in the supplied items."
    )


def _build_payload(events: list[EnrichedEvent]) -> dict[str, Any]:
    layer_counts = Counter(_layer_label(event) for event in events)
    type_counts = Counter(_safe_value(event.normalized_event_type, "unknown") for event in events)
    topic_counts = Counter(_safe_value(event.topic, "unknown") for event in events)
    entity_counts: Counter[str] = Counter()
    platform_counts: Counter[str] = Counter()

    for event in events:
        entity_counts.update(str(entity).strip() for entity in event.entities if str(entity).strip())
        platform_counts.update(str(platform).strip() for platform in event.platforms if str(platform).strip())

    buckets: dict[str, list[EnrichedEvent]] = defaultdict(list)
    for event in events:
        buckets[_bucket_label(event)].append(event)

    bucket_payload = []
    for label, bucket_events in sorted(buckets.items(), key=lambda row: _bucket_sort_key(row[0])):
        representatives = sorted(
            bucket_events,
            key=lambda event: (-int(event.member_count or 0), -len(event.platforms), str(event.latest_pubtime or "")),
        )[:MAX_BUCKET_ITEMS]
        bucket_payload.append(
            {
                "bucket": label,
                "event_count": len(bucket_events),
                "common_types": _top_items(Counter(_safe_value(event.normalized_event_type, "unknown") for event in bucket_events), 8),
                "common_entities": _top_items(_entity_counter(bucket_events), 10),
                "representative_signals": [
                    {
                        "title": _truncate(event.title, MAX_TITLE_CHARS),
                        "brief": _truncate(event.one_sentence, MAX_BRIEF_CHARS),
                        "type": event.normalized_event_type,
                        "entities": event.entities[:5],
                        "platforms": event.platforms[:4],
                    }
                    for event in representatives
                ],
            }
        )

    return {
        "task": "Generate one broad daily AI industry trend observation.",
        "global_signals": {
            "event_count": len(events),
            "layer_distribution": _top_items(layer_counts, 10),
            "type_distribution": _top_items(type_counts, 14),
            "topic_distribution": _top_items(topic_counts, 14),
            "frequent_entities": _top_items(entity_counts, 18),
            "frequent_platforms": _top_items(platform_counts, 12),
        },
        "bucketed_representative_signals": bucket_payload,
        "editorial_requirements": [
            "Use the full eligible pool as the basis, while treating the report selection as examples only.",
            "A macro direction must be supported by repeated events, entities, types, or independent sources; do not elevate an isolated item into a trend.",
            "Do not infer an industry direction that is absent from the supplied distribution.",
            "Avoid naming a single event unless it represents a repeated cross-source pattern.",
            "Prefer precise trend-level language grounded in repeated event types and facts.",
        ],
    }


def _bucket_label(event: EnrichedEvent) -> str:
    if event.report_section in SECTION_LABELS:
        return SECTION_LABELS[event.report_section]
    return _layer_label(event)


def _layer_label(event: EnrichedEvent) -> str:
    return LAYER_LABELS.get(event.content_layer, str(event.content_layer or "unknown"))


def _bucket_sort_key(label: str) -> int:
    order = {
        "今日重点新闻": 0,
        "研究论文与评测": 1,
        "长期方法与资源沉淀": 2,
        "待观察线索": 3,
        "新闻动态与产品落地": 4,
        "研究论文与方法评测": 5,
    }
    return order.get(label, 99)


def _entity_counter(events: list[EnrichedEvent]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for event in events:
        counter.update(str(entity).strip() for entity in event.entities if str(entity).strip())
    return counter


def _top_items(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit) if name]


def _safe_value(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _clean_summary(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.strip().split())
    text = text.lstrip("- ").strip().replace("\ufffd", "")
    if not text:
        return ""
    if not text.endswith(("。", "！", "？", ".", "!", "?")):
        text += "。"
    return text[:520].rstrip()


def _truncate(value: str, max_chars: int) -> str:
    value = " ".join(str(value or "").split())
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"
