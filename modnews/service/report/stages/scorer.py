from __future__ import annotations

from datetime import date, datetime, time, timezone

from modnews.service.report.config import SCORE_WEIGHTS
from modnews.service.report.models import EventCandidate, ScoreBreakdown
from modnews.service.report.rules.scoring_rules import IMPORTANCE_BASE
from modnews.service.report.rules.source_weights import platform_score, source_kind
from modnews.service.report.rules.taxonomy import AI_KEYWORDS, HIGH_IMPACT_TYPES
from modnews.service.report.utils.text import has_any_word
from modnews.service.report.utils.time import ensure_aware

ACTIONABLE_TYPES = {
    "model_release", "product_release", "open_source", "tooling", "framework",
    "library", "benchmark", "hardware", "infrastructure", "policy", "legal",
}
ACTIONABLE_WORDS = {
    "api", "sdk", "github", "repo", "release", "launch", "available", "preview",
    "benchmark", "dataset", "open source", "download", "deploy", "integration",
    "\u5f00\u6e90", "\u53d1\u5e03", "\u4e0a\u7ebf", "\u63a5\u5165", "\u90e8\u7f72", "\u6d4b\u8bd5", "\u8bd5\u7528", "\u57fa\u51c6", "\u6570\u636e\u96c6",
}
FOLLOW_UP_WORDS = {
    "again", "update", "follow-up", "recap", "roundup", "summary", "rumor",
    "\u518d\u6b21", "\u66f4\u65b0", "\u540e\u7eed", "\u6c47\u603b", "\u4f20\u95fb",
}
NOVELTY_WORDS = {
    "first", "new", "launch", "release", "introduce", "announce", "open source",
    "\u9996\u6b21", "\u65b0", "\u53d1\u5e03", "\u63a8\u51fa", "\u5f00\u6e90", "\u4e0a\u7ebf",
}
STRATEGIC_FOCUS_KEYWORDS = {
    "ai_compute_chip": {
        "chip", "semiconductor", "gpu", "hbm", "memory", "wafer", "foundry", "tsmc", "samsung",
        "sk hynix", "nvidia", "cuda", "asic", "tpu", "data center", "datacenter", "inference",
        "compute", "blackwell", "rubin", "gb300", "jetson", "trainium", "accelerator",
        "\u82af\u7247", "\u534a\u5bfc\u4f53", "\u7b97\u529b", "\u63a8\u7406", "\u663e\u5361", "\u6676\u5706", "\u4ee3\u5de5",
        "\u5185\u5b58", "\u5b58\u50a8", "\u6570\u636e\u4e2d\u5fc3", "\u9ad8\u5e26\u5bbd\u5185\u5b58", "\u5c01\u88c5",
        "\u53f0\u79ef\u7535", "\u4e09\u661f", "\u6d77\u529b\u58eb", "\u82f1\u4f1f\u8fbe", "\u534e\u4e3a\u82af\u7247",
    },
    "ai_biomedicine": {
        "biology", "biomedical", "medicine", "drug", "pharma", "chemist", "chemistry", "life science",
        "protein", "genomics", "clinical", "molecule", "molecular", "reaction", "synthesis",
        "therapeutic", "medicinal", "lifescibench", "molecule.one",
        "\u751f\u547d\u79d1\u5b66", "\u751f\u7269", "\u751f\u7269\u533b\u836f", "\u533b\u836f", "\u836f\u7269", "\u5236\u836f",
        "\u5316\u5b66", "\u836f\u7269\u5316\u5b66", "\u86cb\u767d", "\u57fa\u56e0", "\u4e34\u5e8a", "\u5206\u5b50", "\u5408\u6210",
        "\u5b9e\u9a8c\u5ba4", "\u53cd\u5e94", "\u75be\u75c5", "\u6cbb\u7597", "\u836f\u4f01",
    },
}
STRATEGIC_FOCUS_BOOSTS = {
    "ai_compute_chip": {"importance": 8.0, "relevance": 10.0, "actionability": 8.0, "novelty": 3.0},
    "ai_biomedicine": {"importance": 8.0, "relevance": 12.0, "actionability": 7.0, "novelty": 5.0},
}


def score_event(candidate: EventCandidate, normalized_type: str, report_date: date) -> ScoreBreakdown:
    focuses = _strategic_focuses(candidate)
    importance = _importance_score(candidate, normalized_type, focuses)
    source = _source_score(candidate)
    freshness = _freshness_score(candidate, report_date)
    relevance = _relevance_score(candidate, focuses)
    actionability = _actionability_score(candidate, normalized_type, focuses)
    novelty = _novelty_score(candidate, normalized_type, focuses)
    risk_penalty = _risk_penalty(candidate)

    final = (
        importance * SCORE_WEIGHTS.impact
        + source * SCORE_WEIGHTS.source
        + freshness * SCORE_WEIGHTS.freshness
        + relevance * SCORE_WEIGHTS.relevance
        + actionability * SCORE_WEIGHTS.actionability
        + novelty * SCORE_WEIGHTS.novelty
        - risk_penalty
    )

    final = round(max(0.0, min(100.0, final)), 2)
    focus_reason = ", focus=" + "+".join(focuses) if focuses else ""
    reason = (
        f"impact={importance:.0f}, source={source:.0f}, freshness={freshness:.0f}, "
        f"relevance={relevance:.0f}, actionability={actionability:.0f}, "
        f"novelty={novelty:.0f}, risk_penalty={risk_penalty:.0f}{focus_reason}"
    )
    return ScoreBreakdown(
        importance_score=round(importance, 2),
        source_score=round(source, 2),
        freshness_score=round(freshness, 2),
        relevance_score=round(relevance, 2),
        actionability_score=round(actionability, 2),
        novelty_score=round(novelty, 2),
        risk_penalty=round(risk_penalty, 2),
        final_score=final,
        score_reason=reason,
    )


def _importance_score(candidate: EventCandidate, normalized_type: str, focuses: list[str]) -> float:
    score = IMPORTANCE_BASE.get(normalized_type, IMPORTANCE_BASE["unknown"])
    distinct_platform_count = len({platform.strip().lower() for platform in candidate.platforms if platform.strip()})
    if distinct_platform_count >= 2:
        score += min(8.0, 3.0 * distinct_platform_count)
    if normalized_type in HIGH_IMPACT_TYPES and candidate.confidence >= 0.9:
        score += 5.0
    if candidate.member_count >= 4:
        score += 4.0
    for focus in focuses:
        score += STRATEGIC_FOCUS_BOOSTS[focus]["importance"]
    if len(focuses) >= 2:
        score += 3.0
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
    official_bonus = 4.0 if "official" in source_kinds else 0.0
    return _clamp(base + diversity_bonus + official_bonus)


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


def _relevance_score(candidate: EventCandidate, focuses: list[str]) -> float:
    haystack = _haystack(candidate)
    score = 88.0 if has_any_word(haystack, AI_KEYWORDS) else 52.0
    if focuses and score < 82.0:
        score = 82.0
    for focus in focuses:
        score += STRATEGIC_FOCUS_BOOSTS[focus]["relevance"]
    return _clamp(score)


def _actionability_score(candidate: EventCandidate, normalized_type: str, focuses: list[str]) -> float:
    haystack = _haystack(candidate)
    score = 45.0
    if normalized_type in ACTIONABLE_TYPES:
        score += 22.0
    if has_any_word(haystack, ACTIONABLE_WORDS):
        score += 18.0
    if normalized_type in {"policy", "legal", "hardware", "infrastructure"}:
        score += 8.0
    for focus in focuses:
        score += STRATEGIC_FOCUS_BOOSTS[focus]["actionability"]
    if candidate.source_items and any((source.url or "").strip() for source in candidate.source_items):
        score += 5.0
    return _clamp(score)


def _novelty_score(candidate: EventCandidate, normalized_type: str, focuses: list[str]) -> float:
    haystack = _haystack(candidate)
    score = 58.0
    if normalized_type in {"model_release", "product_release", "open_source", "research", "benchmark"}:
        score += 14.0
    if has_any_word(haystack, NOVELTY_WORDS):
        score += 16.0
    for focus in focuses:
        score += STRATEGIC_FOCUS_BOOSTS[focus]["novelty"]
    if has_any_word(haystack, FOLLOW_UP_WORDS):
        score -= 14.0
    if candidate.member_count >= 5:
        score += 4.0
    return _clamp(score)


def _risk_penalty(candidate: EventCandidate) -> float:
    penalty = 0.0
    distinct_platforms = {platform.strip().lower() for platform in candidate.platforms if platform.strip()}
    source_kinds = {source_kind(platform) for platform in distinct_platforms}
    if len(distinct_platforms) <= 1 and "official" not in source_kinds:
        penalty += 8.0
    if "community" in source_kinds and len(distinct_platforms) <= 1:
        penalty += 8.0
    if candidate.confidence < 0.7:
        penalty += 8.0
    if candidate.latest_pubtime is None:
        penalty += 6.0
    if _has_possible_mismatch(candidate):
        penalty += 18.0
    return min(penalty, 40.0)


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


def _strategic_focuses(candidate: EventCandidate) -> list[str]:
    haystack = _haystack(candidate)
    focuses: list[str] = []
    for focus, keywords in STRATEGIC_FOCUS_KEYWORDS.items():
        if has_any_word(haystack, keywords):
            focuses.append(focus)
    return focuses


def _haystack(candidate: EventCandidate) -> str:
    return " ".join(
        [
            candidate.event_label,
            candidate.event_summary,
            candidate.event_type,
            " ".join(candidate.representative_titles),
            " ".join(candidate.key_entities),
        ]
    ).lower()


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))
