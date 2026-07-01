from __future__ import annotations

from datetime import date, datetime, time, timezone

from src.config import SCORE_WEIGHTS
from src.models import EventCandidate, ScoreBreakdown
from src.rules.scoring_rules import IMPORTANCE_BASE
from src.rules.source_weights import platform_score, source_kind
from src.rules.taxonomy import AI_KEYWORDS, HIGH_IMPACT_TYPES
from src.utils.text import has_any_word
from src.utils.time import ensure_aware


def score_event(candidate: EventCandidate, normalized_type: str, report_date: date) -> ScoreBreakdown:
    importance = _importance_score(candidate, normalized_type)
    source = _source_score(candidate)
    freshness = _freshness_score(candidate, report_date)
    relevance = _relevance_score(candidate)
    final = (
        importance * SCORE_WEIGHTS.importance
        + source * SCORE_WEIGHTS.source
        + freshness * SCORE_WEIGHTS.freshness
        + relevance * SCORE_WEIGHTS.relevance
    )

    distinct_platforms = {platform.strip().lower() for platform in candidate.platforms if platform.strip()}
    if len(distinct_platforms) <= 1 and "official" not in {source_kind(p) for p in distinct_platforms}:
        final -= 8.0
    if _has_possible_mismatch(candidate):
        final -= 18.0

    final = round(max(0.0, min(100.0, final)), 2)
    reason = (
        f"importance={importance:.0f}, source={source:.0f}, "
        f"freshness={freshness:.0f}, relevance={relevance:.0f}"
    )
    return ScoreBreakdown(
        importance_score=round(importance, 2),
        source_score=round(source, 2),
        freshness_score=round(freshness, 2),
        relevance_score=round(relevance, 2),
        final_score=final,
        score_reason=reason,
    )


def _importance_score(candidate: EventCandidate, normalized_type: str) -> float:
    score = IMPORTANCE_BASE.get(normalized_type, IMPORTANCE_BASE["unknown"])
    distinct_platform_count = len({platform.strip().lower() for platform in candidate.platforms if platform.strip()})
    if distinct_platform_count >= 2:
        score += min(8.0, 3.0 * distinct_platform_count)
    if normalized_type in HIGH_IMPACT_TYPES and candidate.confidence >= 0.9:
        score += 5.0
    if candidate.confidence < 0.7:
        score -= 10.0
    return _clamp(score)


def _source_score(candidate: EventCandidate) -> float:
    if not candidate.platforms:
        return 25.0
    platforms = sorted({platform.strip().lower() for platform in candidate.platforms if platform.strip()})
    scores = [platform_score(platform) for platform in platforms]
    base = max(scores) if scores else 25.0
    source_kinds = {source_kind(platform) for platform in platforms}

    if len(platforms) <= 1:
        if "official" in source_kinds:
            return min(base, 88.0)
        if "authority_media" in source_kinds:
            return min(base, 76.0)
        if "chinese_media" in source_kinds:
            return min(base, 66.0)
        if "community" in source_kinds:
            return min(base, 42.0)
        return min(base, 58.0)

    diversity_bonus = min(12.0, (len(platforms) - 1) * 4.0)
    return _clamp(base + diversity_bonus)


def _freshness_score(candidate: EventCandidate, report_date: date) -> float:
    if candidate.latest_pubtime is None:
        return 20.0
    report_dt = datetime.combine(report_date, time(hour=8), tzinfo=timezone.utc)
    event_dt = ensure_aware(candidate.latest_pubtime).astimezone(timezone.utc)
    age_hours = max(0.0, (report_dt - event_dt).total_seconds() / 3600)
    if age_hours <= 24:
        return 100.0
    if age_hours <= 72:
        return 82.0
    if age_hours <= 24 * 7:
        return 62.0
    if age_hours <= 24 * 30:
        return 34.0
    return 12.0


def _relevance_score(candidate: EventCandidate) -> float:
    haystack = " ".join(
        [
            candidate.event_label,
            candidate.event_summary,
            candidate.event_type,
            " ".join(candidate.representative_titles),
            " ".join(candidate.key_entities),
        ]
    )
    if has_any_word(haystack, AI_KEYWORDS):
        return 88.0
    return 52.0


def _has_possible_mismatch(candidate: EventCandidate) -> bool:
    if not candidate.source_items:
        return False
    title = candidate.event_label.lower()
    if not title:
        return False
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


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))