from __future__ import annotations

from src.models import EventCandidate, VerifyStatus
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
    if text_quality in {"bad", "missing"}:
        return "needs_review", "文本存在乱码或缺失，需要人工复核。"
    if "confidence_out_of_range" in warnings:
        return "needs_review", "confidence 超出有效范围。"
    if has_any_word(haystack, RUMOR_WORDS):
        return "rumor", "包含传闻或未确认措辞，适合进入待观察线索。"
    return "single_source", "等待原文回溯结果确认。"
