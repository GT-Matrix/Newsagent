from __future__ import annotations

from src.models import EventCandidate, VerifyStatus
from src.rules.source_weights import source_kind
from src.rules.taxonomy import RUMOR_WORDS
from src.utils.text import has_any_word


def verify_event(candidate: EventCandidate, text_quality: str) -> tuple[VerifyStatus, str]:
    warnings = set(candidate.original.get("_validation_warnings", []))
    haystack = " ".join(
        [
            candidate.event_label,
            candidate.event_summary,
            " ".join(candidate.representative_titles),
            " ".join(candidate.key_entities),
        ]
    )
    platforms = {platform.strip().lower() for platform in candidate.platforms if platform.strip()}
    source_kinds = {source_kind(platform) for platform in platforms}

    if text_quality in {"bad", "missing"}:
        return "needs_review", "文本存在乱码或缺失，需要人工复核。"
    if candidate.latest_pubtime is None:
        return "needs_review", "缺少发布时间，不能稳定判断时效性。"
    if "confidence_out_of_range" in warnings:
        return "needs_review", "confidence 超出有效范围。"
    if _has_possible_mismatch(candidate):
        return "needs_review", "事件标题与来源标题明显不一致，疑似上游错聚类。"
    if has_any_word(haystack, RUMOR_WORDS):
        return "rumor", "包含传闻或未确认措辞，适合进入待观察线索。"
    if "community" in source_kinds and len(platforms) == 1:
        return "rumor", "仅来自社区或论坛来源。"
    if "official" in source_kinds and platforms:
        return "verified", "包含官方来源。"
    if len(platforms) >= 2 and source_kinds & {"authority_media", "chinese_media"}:
        return "verified", "来自多个平台且包含媒体来源。"
    return "single_source", "单一平台来源，已保留但需要展示来源状态。"


def _has_possible_mismatch(candidate: EventCandidate) -> bool:
    if not candidate.source_items:
        return False
    title = candidate.event_label.lower()
    tokens = {token for token in title.replace("-", " ").replace("/", " ").split() if len(token) >= 4}
    if not tokens:
        return False
    checked = 0
    misses = 0
    for source in candidate.source_items[:5]:
        source_title = (source.title or "").lower()
        if not source_title:
            continue
        checked += 1
        if not any(token in source_title for token in tokens):
            misses += 1
    return checked > 0 and misses == checked