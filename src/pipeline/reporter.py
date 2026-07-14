from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import re

from src.config import REPORT_LIMITS
from src.models import EnrichedEvent, ReportSection

POLICY_TYPES = {"policy", "legal", "company_policy"}
PAPER_PLATFORMS = {"arxiv", "huggingface_papers_trending"}
PAPER_TYPES = {"research", "benchmark", "paper"}
PAPER_WORDS = {
    "paper", "arxiv", "benchmark", "dataset", "research", "method", "architecture",
    "\u8bba\u6587", "\u57fa\u51c6", "\u6570\u636e\u96c6", "\u7814\u7a76", "\u65b9\u6cd5", "\u67b6\u6784",
}
REUSABLE_ASSET_WORDS = {
    "github", "repo", "repository", "open source", "opensource", "framework", "toolkit", "sdk",
    "library", "dataset", "benchmark", "code", "agent", "memory", "retrieval", "ocr",
    "\u5f00\u6e90", "\u4ed3\u5e93", "\u6846\u67b6", "\u5de5\u5177", "\u6570\u636e\u96c6", "\u57fa\u51c6",
    "\u4ee3\u7801", "\u667a\u80fd\u4f53", "\u8bb0\u5fc6", "\u68c0\u7d22",
}
COMPUTE_FOCUS_WORDS = {
    "chip", "gpu", "hbm", "blackwell", "rubin", "jetson", "inference", "compute", "datacenter",
    "data center", "accelerator", "semiconductor", "nvidia", "broadcom", "tsmc",
    "\u82af\u7247", "\u7b97\u529b", "\u63a8\u7406", "\u534a\u5bfc\u4f53", "\u6570\u636e\u4e2d\u5fc3",
    "\u82f1\u4f1f\u8fbe", "\u5b58\u50a8", "\u6676\u5706",
}
BIOMED_FOCUS_WORDS = {
    "biology", "biomedical", "medicine", "drug", "pharma", "life science", "protein", "genomics",
    "clinical", "molecule", "chemistry", "bionemo", "gene",
    "\u751f\u7269", "\u751f\u7269\u533b\u836f", "\u533b\u836f", "\u751f\u547d\u79d1\u5b66", "\u836f\u7269",
    "\u5236\u836f", "\u86cb\u767d", "\u57fa\u56e0", "\u4e34\u5e8a", "\u5206\u5b50", "\u5316\u5b66",
}
TOP_TYPE_LIMITS = {
    "model_release": 3,
    "product_release": 2,
    "company_business": 2,
    "company_policy": 2,
    "policy": 2,
    "legal": 2,
    "funding": 2,
    "partnership": 2,
}
DEEP_ASSET_EXCLUDE = {"course", "academy", "education", "\u8bfe\u7a0b", "\u6559\u80b2"}
ASSET_TYPES = {"open_source", "tooling", "framework", "library", "paper", "research"}
ASSET_WORDS = {
    "github", "repo", "repository", "open source", "opensource", "framework", "toolkit", "sdk", "library",
    "benchmark", "dataset", "paper", "arxiv", "model card", "readme",
    "\u5f00\u6e90", "\u4ed3\u5e93", "\u6846\u67b6", "\u5de5\u5177", "\u6570\u636e\u96c6", "\u8bba\u6587", "\u57fa\u51c6",
}
WATCH_TYPES = {"rumor", "company_business", "company_policy", "funding", "partnership", "product_release", "model_release"}
SOFT_COMMENTARY_WORDS = {
    "questions", "criticizes", "warns", "doubts", "opinion", "skeptical",
    "\u8d28\u7591", "\u6000\u7591", "\u8b66\u544a", "\u6279\u8bc4", "\u89c2\u70b9", "\u62c5\u5fe7",
}


def assign_report_sections(events: list[EnrichedEvent]) -> list[EnrichedEvent]:
    for event in events:
        event.should_include_report = False
        event.report_section = None
        event.report_reason = ""
        event.report_tags = _build_report_tags(event)
        event.section_scores = _section_scores(event)

    public_events = [event for event in events if event.verify_status != "needs_review"]
    top_candidates = _sort_for_section(
        [event for event in public_events if event.content_layer == "news" and _is_top_news_candidate(event)],
        "top_news",
    )
    insights = _sort_for_section([event for event in public_events if _is_research_insight_candidate(event)], "insight")
    deep_assets = _sort_for_section(
        [
            event
            for event in public_events
            if _is_real_deep_asset(event)
            and event.verify_status in {"verified", "single_source"}
            and event.final_score >= 60
        ],
        "deep_asset",
    )
    selected_top = _select_top_news(top_candidates, REPORT_LIMITS.top_news_max)
    selected_ids = {event.event_id for event in selected_top}
    selected_insights = _select_research_section(insights, selected_ids, REPORT_LIMITS.insight_max)
    selected_ids.update(event.event_id for event in selected_insights)
    selected_assets = _select_asset_section(deep_assets, selected_ids, REPORT_LIMITS.deep_asset_max)

    _mark(selected_top, "top_news", "\u8fbe\u5230\u91cd\u70b9\u65b0\u95fb\u9608\u503c\uff0c\u5e76\u901a\u8fc7\u7c7b\u578b\u3001\u5b9e\u4f53\u548c\u6765\u6e90\u591a\u6837\u6027\u63a7\u5236\u3002")
    _mark(selected_insights, "insight", "\u8fbe\u5230\u7814\u7a76\u3001\u8bc4\u6d4b\u6216\u8bba\u6587\u4fe1\u53f7\u5165\u9009\u9608\u503c\u3002")
    _mark(selected_assets, "deep_asset", "\u5177\u5907\u957f\u671f\u65b9\u6cd5\u3001\u5de5\u5177\u6216\u6280\u672f\u8d44\u4ea7\u6c89\u6dc0\u4ef7\u503c\u3002")
    return events


def build_report_markdown(events: list[EnrichedEvent], report_date: date, trend_summary: str | None = None) -> str:
    sections = _report_sections(events)
    lines: list[str] = [f"# AI \u60c5\u62a5\u65e9\u62a5 - {report_date.isoformat()}", ""]
    lines.extend(_render_event_section("\u4e00\u3001\u4eca\u65e5\u91cd\u70b9\u65b0\u95fb", sections["top_news"]))
    lines.extend(_render_event_section("\u4e8c\u3001\u7814\u7a76\u3001\u8bc4\u6d4b\u4e0e\u8bba\u6587", sections["insight"]))
    lines.extend(_render_event_section("\u4e09\u3001\u957f\u671f\u65b9\u6cd5\u4e0e\u8d44\u6e90\u6c89\u6dc0", sections["deep_asset"], empty="\u4eca\u65e5\u6682\u65e0\u8fbe\u5230\u63a8\u9001\u9608\u503c\u7684\u6df1\u5c42\u8d44\u6e90\u3002"))
    lines.extend(_render_trends(events, trend_summary))
    lines.append("")
    lines.append("> \u8bf4\u660e\uff1a\u672c\u62a5\u544a\u9762\u5411\u7fa4\u5185\u9605\u8bfb\uff1b\u8bc4\u5206\u3001\u680f\u76ee\u5206\u548c\u6807\u7b7e\u7b49\u8c03\u8bd5\u4fe1\u606f\u5df2\u5355\u72ec\u5199\u5165 daily_report_debug.md \u548c report_candidates.json\u3002")
    return "\n".join(lines).strip() + "\n"


def build_debug_report_markdown(events: list[EnrichedEvent], report_date: date, trend_summary: str | None = None) -> str:
    sections = _report_sections(events)
    lines: list[str] = [f"# AI \u60c5\u62a5\u65e9\u62a5\u8c03\u8bd5\u7248 - {report_date.isoformat()}", ""]
    lines.extend(_render_event_section("\u4e00\u3001\u4eca\u65e5\u91cd\u70b9\u65b0\u95fb", sections["top_news"], debug=True))
    lines.extend(_render_event_section("\u4e8c\u3001\u7814\u7a76\u3001\u8bc4\u6d4b\u4e0e\u8bba\u6587", sections["insight"], debug=True))
    lines.extend(_render_event_section("\u4e09\u3001\u957f\u671f\u65b9\u6cd5\u4e0e\u8d44\u6e90\u6c89\u6dc0", sections["deep_asset"], debug=True))
    lines.extend(_render_trends(events, trend_summary))
    return "\n".join(lines).strip() + "\n"


def _report_sections(events: list[EnrichedEvent]) -> dict[str, list[EnrichedEvent]]:
    return {
        "top_news": [event for event in events if event.report_section == "top_news"],
        "insight": [event for event in events if event.report_section == "insight"],
        "deep_asset": [event for event in events if event.report_section == "deep_asset"],
        "watchlist": [event for event in events if event.report_section == "watchlist"],
    }

def report_candidates_payload(events: list[EnrichedEvent]) -> dict[str, list[dict[str, object]]]:
    payload: dict[str, list[dict[str, object]]] = {"top_news": [], "insight": [], "deep_asset": [], "unselected_high_score": []}
    for section in ("top_news", "insight", "deep_asset"):
        payload[section] = [event.to_dict() for event in events if event.report_section == section]
    payload["unselected_high_score"] = [
        event.to_dict()
        for event in events
        if event.report_section is None and event.verify_status != "needs_review" and event.final_score >= 60
    ][:50]
    return payload


def review_candidates_payload(events: list[EnrichedEvent]) -> list[dict[str, object]]:
    return [event.to_dict() for event in events if event.verify_status == "needs_review" or "source_items_missing" in event.warnings]


def _section_scores(event: EnrichedEvent) -> dict[str, float]:
    paper_bonus = 6.0 if _is_paper_event(event) else 0.0
    asset_bonus = 5.0 if _has_reusable_asset_signal(event) else 0.0
    top_news = event.importance_score * 0.58 + event.source_score * 0.06 + event.freshness_score * 0.12 + event.relevance_score * 0.13 + event.actionability_score * 0.06 + event.novelty_score * 0.05 - event.risk_penalty * 0.50
    insight = event.novelty_score * 0.34 + event.relevance_score * 0.27 + event.source_score * 0.08 + event.importance_score * 0.21 + event.freshness_score * 0.10 - event.risk_penalty * 0.38 + paper_bonus
    deep_asset = event.actionability_score * 0.42 + event.novelty_score * 0.22 + event.source_score * 0.08 + event.relevance_score * 0.16 + event.importance_score * 0.12 - event.risk_penalty * 0.34 + asset_bonus
    watchlist = event.importance_score * 0.42 + event.novelty_score * 0.14 + event.actionability_score * 0.14 + event.freshness_score * 0.14 + event.relevance_score * 0.16 - max(event.risk_penalty - 18.0, 0.0) * 0.50
    return {"top_news": _clamp_score(top_news), "insight": _clamp_score(insight), "deep_asset": _clamp_score(deep_asset), "watchlist": _clamp_score(watchlist)}



def _strategic_section_bonus(event: EnrichedEvent) -> float:
    reason = event.score_reason.lower()
    bonus = 0.0
    if "ai_compute_chip" in reason:
        bonus += 4.0
    if "ai_biomedicine" in reason:
        bonus += 4.0
    return min(bonus, 7.0)

def _sort_for_section(events: list[EnrichedEvent], section: str) -> list[EnrichedEvent]:
    return sorted(events, key=lambda event: (event.section_scores.get(section, 0.0), event.final_score, event.importance_score, event.source_score), reverse=True)


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _is_top_news_candidate(event: EnrichedEvent) -> bool:
    if event.verify_status == "rumor":
        return False
    if event.verify_status == "single_source" and _is_soft_commentary(event):
        return False
    if event.verify_status == "single_source" and event.evidence_summary.get("soft_commentary"):
        return False
    if "low_news_value" in event.score_reason:
        return False
    if event.risk_penalty > 18:
        return False
    if _is_incomplete_title(event.title):
        return False
    if event.freshness_score < 62:
        return False
    if event.final_score >= 60:
        return True
    return False


def _is_incomplete_title(title: str) -> bool:
    compact = " ".join(title.split())
    return len(compact) < 10


def _select_top_news(events: list[EnrichedEvent], limit: int) -> list[EnrichedEvent]:
    selected: list[EnrichedEvent] = []
    seen: set[str] = set()
    type_counts: defaultdict[str, int] = defaultdict(int)
    entity_counts: defaultdict[str, int] = defaultdict(int)
    platform_counts: defaultdict[str, int] = defaultdict(int)
    for event in events:
        if event.event_id in seen:
            continue
        event_type = event.normalized_event_type
        type_limit = TOP_TYPE_LIMITS.get(event_type, 3)
        if event_type in POLICY_TYPES:
            type_limit = 2
        if type_counts[event_type] >= type_limit:
            continue
        main_entity = _main_entity(event)
        if main_entity and entity_counts[main_entity] >= 2:
            continue
        main_platform = _main_platform(event)
        if main_platform and platform_counts[main_platform] >= 2:
            continue
        if _has_near_duplicate_topic(event, selected):
            continue
        selected.append(event)
        seen.add(event.event_id)
        type_counts[event_type] += 1
        if main_entity:
            entity_counts[main_entity] += 1
        if main_platform:
            platform_counts[main_platform] += 1
        if len(selected) >= limit:
            break
    return selected


def _dedupe_section(
    events: list[EnrichedEvent],
    excluded_ids: set[str],
    limit: int,
    *,
    platform_limit: int | None = None,
    community_single_source_limit: int | None = None,
) -> list[EnrichedEvent]:
    selected: list[EnrichedEvent] = []
    seen_entities: set[str] = set()
    platform_counts: defaultdict[str, int] = defaultdict(int)
    community_single_source_count = 0
    for event in events:
        if event.event_id in excluded_ids:
            continue
        entity = _main_entity(event)
        if entity and entity in seen_entities:
            continue
        platform = _main_platform(event)
        if platform_limit is not None and platform and platform_counts[platform] >= platform_limit:
            continue
        is_community_single_source = event.verify_status == "single_source" and _is_community_only(event)
        if community_single_source_limit is not None and is_community_single_source and community_single_source_count >= community_single_source_limit:
            continue
        selected.append(event)
        if entity:
            seen_entities.add(entity)
        if platform:
            platform_counts[platform] += 1
        if is_community_single_source:
            community_single_source_count += 1
        if len(selected) >= limit:
            break
    return selected


def _select_research_section(events: list[EnrichedEvent], excluded_ids: set[str], limit: int) -> list[EnrichedEvent]:
    eligible = [event for event in events if event.event_id not in excluded_ids]
    selected = _dedupe_section(eligible, set(), limit, platform_limit=2)
    paper_candidates = [event for event in eligible if _is_paper_event(event) and event.section_scores.get("insight", 0.0) >= 58]
    trending_papers = [event for event in eligible if _is_trending_paper_event(event) and event.section_scores.get("insight", 0.0) >= 58]
    if paper_candidates and not any(_is_paper_event(event) for event in selected):
        selected = _force_include_candidate(selected, paper_candidates[0], limit, section="insight")
    if trending_papers and not any(_is_trending_paper_event(event) for event in selected):
        selected = _force_include_candidate(selected, trending_papers[0], limit, section="insight")
    return _sort_for_section(_dedupe_keep_order(selected), "insight")[:limit]


def _select_asset_section(events: list[EnrichedEvent], excluded_ids: set[str], limit: int) -> list[EnrichedEvent]:
    eligible = [event for event in events if event.event_id not in excluded_ids]
    selected = _dedupe_section(eligible, set(), limit, platform_limit=2)
    reusable_papers = [
        event
        for event in eligible
        if _is_paper_event(event) and _has_reusable_asset_signal(event) and event.section_scores.get("deep_asset", 0.0) >= 58
    ]
    trending_assets = [event for event in reusable_papers if _is_trending_paper_event(event)]
    if reusable_papers and not any(_is_paper_event(event) for event in selected):
        selected = _force_include_candidate(selected, reusable_papers[0], limit, section="deep_asset")
    if trending_assets and not any(_is_trending_paper_event(event) for event in selected):
        selected = _force_include_candidate(selected, trending_assets[0], limit, section="deep_asset")
    return _sort_for_section(_dedupe_keep_order(selected), "deep_asset")[:limit]


def _force_include_candidate(
    selected: list[EnrichedEvent],
    candidate: EnrichedEvent,
    limit: int,
    *,
    section: str,
) -> list[EnrichedEvent]:
    if any(event.event_id == candidate.event_id for event in selected):
        return selected
    if len(selected) < limit:
        return selected + [candidate]
    replace_index = _weakest_replace_index(selected, prefer_non_paper=True, section=section)
    if replace_index is None:
        replace_index = _weakest_replace_index(selected, prefer_non_paper=False, section=section)
    if replace_index is not None:
        selected = list(selected)
        selected[replace_index] = candidate
    return selected


def _weakest_replace_index(events: list[EnrichedEvent], *, prefer_non_paper: bool, section: str) -> int | None:
    candidates = [
        (index, event.section_scores.get(section, event.final_score))
        for index, event in enumerate(events)
        if not prefer_non_paper or not _is_paper_event(event)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[1])[0]


def _dedupe_keep_order(events: list[EnrichedEvent]) -> list[EnrichedEvent]:
    seen: set[str] = set()
    result: list[EnrichedEvent] = []
    for event in events:
        if event.event_id in seen:
            continue
        seen.add(event.event_id)
        result.append(event)
    return result


def _is_watchlist_candidate(event: EnrichedEvent) -> bool:
    if event.verify_status == "rumor" and event.importance_score >= 55:
        return True
    if event.verify_status == "single_source" and event.final_score >= 74 and event.importance_score >= 70:
        return True
    if "community_only" in event.report_tags and event.final_score >= 68 and event.importance_score >= 70:
        return True
    if event.normalized_event_type in WATCH_TYPES and event.risk_penalty >= 12 and event.final_score >= 65:
        return True
    return False


def _is_real_deep_asset(event: EnrichedEvent) -> bool:
    text = f"{event.title} {event.one_sentence} {event.normalized_event_type} {' '.join(event.entities)}".lower()
    if any(word in text for word in DEEP_ASSET_EXCLUDE):
        return False
    has_asset_type = event.normalized_event_type in ASSET_TYPES
    has_asset_word = any(word in text for word in ASSET_WORDS) or _has_reusable_asset_signal(event)
    has_link = any(str(source.get("url") or "").strip() for source in event.source_items)
    high_utility = event.actionability_score >= 70 or event.novelty_score >= 72 or (_is_paper_event(event) and event.final_score >= 52)
    link_can_support_asset = event.normalized_event_type in {"open_source", "tooling", "framework", "library"}
    return has_asset_type and (has_asset_word or (link_can_support_asset and has_link)) and high_utility and event.risk_penalty <= 18


def _is_research_insight_candidate(event: EnrichedEvent) -> bool:
    if event.verify_status not in {"verified", "single_source"} or event.risk_penalty > 18:
        return False
    if event.final_score < 60:
        return False
    if not _has_substantive_summary(event):
        return False
    if event.content_layer == "insight" and event.final_score >= 58:
        return True
    if event.normalized_event_type in PAPER_TYPES and event.final_score >= 56:
        return True
    if _is_paper_event(event) and event.final_score >= 50 and event.source_score >= 70:
        return True
    return False


def _is_paper_event(event: EnrichedEvent) -> bool:
    platforms = {platform.strip().lower() for platform in event.platforms if platform}
    if platforms & PAPER_PLATFORMS:
        return True
    text = f"{event.title} {event.one_sentence} {event.normalized_event_type} {' '.join(event.entities)}".lower()
    return event.normalized_event_type in PAPER_TYPES and any(word in text for word in PAPER_WORDS)


def _is_trending_paper_event(event: EnrichedEvent) -> bool:
    return any(platform.strip().lower() == "huggingface_papers_trending" for platform in event.platforms if platform)


def _has_reusable_asset_signal(event: EnrichedEvent) -> bool:
    text = f"{event.title} {event.one_sentence} {event.why_important} {event.normalized_event_type} {' '.join(event.entities)}".lower()
    return any(word in text for word in REUSABLE_ASSET_WORDS)


def _is_direct_asset_link(url: str) -> bool:
    host = url.lower().split("/", 3)[2] if url.startswith(("http://", "https://")) and len(url.split("/", 3)) >= 3 else ""
    return host in {"github.com", "huggingface.co", "arxiv.org", "pypi.org", "npmjs.com"}


def _has_substantive_summary(event: EnrichedEvent) -> bool:
    brief = " ".join(event.one_sentence.split())
    generic = {"\u66f4\u65b0\u7814\u7a76\u8fdb\u5c55\u3002", "\u53d1\u5e03\u7814\u7a76\u8fdb\u5c55\u3002", "\u7814\u7a76\u8fdb\u5c55\u3002"}
    return len(brief) >= 20 and brief not in generic


def _build_report_tags(event: EnrichedEvent) -> list[str]:
    tags: set[str] = {event.normalized_event_type, event.content_layer, event.verify_status}
    if event.final_score >= 80:
        tags.add("high_score")
    if event.actionability_score >= 70:
        tags.add("actionable")
    if event.novelty_score >= 72:
        tags.add("novel")
    if event.risk_penalty >= 12:
        tags.add("risk")
    if event.source_score >= 80:
        tags.add("strong_source")
    if event.verify_status == "single_source":
        tags.add("single_source")
    if event.platforms and len({platform.lower() for platform in event.platforms}) == 1:
        tags.add("single_platform")
    if _is_community_only(event):
        tags.add("community_only")
    if _is_real_deep_asset(event):
        tags.add("asset_candidate")
    if _is_top_news_candidate(event):
        tags.add("top_news_candidate")
    return sorted(tags)


def _is_community_only(event: EnrichedEvent) -> bool:
    platforms = {platform.lower() for platform in event.platforms if platform}
    if not platforms:
        return False
    community_hints = {"linux_do", "hacker", "product", "reddit", "github", "aihot", "v2ex", "juejin", "coolapk"}
    return all(any(hint in platform for hint in community_hints) for platform in platforms)


def _is_soft_commentary(event: EnrichedEvent) -> bool:
    platforms = {platform.lower() for platform in event.platforms if platform}
    if any(platform in {"openai", "anthropic", "google-deepmind", "nvidia", "aws-ml", "mistral", "huggingface"} for platform in platforms):
        return False
    text = f"{event.title} {event.one_sentence}".lower()
    return any(word in text for word in SOFT_COMMENTARY_WORDS)


def _has_near_duplicate_topic(event: EnrichedEvent, selected: list[EnrichedEvent]) -> bool:
    event_tokens = _topic_tokens(event.title)
    if len(event_tokens) < 3:
        return False
    event_entity = _main_entity(event)
    event_platform = _main_platform(event)
    for existing in selected:
        if event_platform and event_platform != _main_platform(existing) and event_entity != _main_entity(existing):
            continue
        existing_tokens = _topic_tokens(existing.title)
        if len(existing_tokens) < 3:
            continue
        overlap = len(event_tokens & existing_tokens) / max(1, min(len(event_tokens), len(existing_tokens)))
        if overlap >= 0.6:
            return True
    return False


def _topic_tokens(text: str) -> set[str]:
    stopwords = {
        "发布", "推出", "提供", "新增", "实现", "方案", "模型", "企业", "the", "and", "for", "with",
        "release", "launch", "announces", "introduces",
    }
    tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,}", text)}
    for word in stopwords:
        if word in text:
            tokens.add(word)
    return {token for token in tokens if token not in stopwords}


def _main_entity(event: EnrichedEvent) -> str:
    for entity in event.entities:
        normalized = entity.strip().lower()
        if normalized:
            return normalized
    return ""


def _main_platform(event: EnrichedEvent) -> str:
    for platform in event.platforms:
        normalized = platform.strip().lower()
        if normalized:
            return normalized
    return ""


def _mark(events: list[EnrichedEvent], section: ReportSection, reason: str) -> None:
    for event in events:
        event.should_include_report = True
        event.report_section = section
        event.report_reason = reason
        if section not in event.report_tags:
            event.report_tags.append(section)
            event.report_tags.sort()


def _render_event_section(
    title: str,
    events: list[EnrichedEvent],
    empty: str = "\u4eca\u65e5\u6682\u65e0\u8fbe\u6807\u5185\u5bb9\u3002",
    *,
    debug: bool = False,
) -> list[str]:
    lines = [f"## {title}", ""]
    if not events:
        lines.extend([empty, ""])
        return lines
    for index, event in enumerate(events, start=1):
        sources = _render_sources(event)
        status = _status_label(event.verify_status)
        evidence_label = _evidence_label(event)
        lines.append(f"{index}. **{event.title}**")
        lines.append(f"   - \u7b80\u62a5\uff1a{event.one_sentence}")
        lines.append(f"   - \u4e3a\u4ec0\u4e48\u91cd\u8981\uff1a{event.why_important}")
        lines.append(f"   - \u6765\u6e90\uff1a{sources}")
        if debug:
            lines.append(f"   - \u72b6\u6001\uff1a{status}\uff1b\u8bc1\u636e\uff1a{evidence_label}")
            tags = "\u3001".join(event.report_tags[:8])
            section_score = event.section_scores.get(event.report_section or "", event.final_score)
            lines.append(f"   - Debug\uff1a\u603b\u5206 {event.final_score:.1f}\uff1b\u680f\u76ee\u5206 {section_score:.1f}\uff1b\u7c7b\u578b {event.normalized_event_type}\uff1b\u6807\u7b7e {tags}")
            if event.warnings:
                lines.append(f"   - Warnings\uff1a{', '.join(event.warnings[:5])}")
        else:
            lines.append(f"   - \u72b6\u6001\uff1a{status}")
        lines.append("")
    return lines
def _render_sources(event: EnrichedEvent) -> str:
    if not event.source_items:
        return ", ".join(event.platforms) if event.platforms else "unknown"
    rendered: list[str] = []
    seen: set[str] = set()
    for source in event.source_items:
        platform = str(source.get("platform") or "unknown")
        url = str(source.get("url") or "")
        key = url or platform
        if key in seen:
            continue
        seen.add(key)
        rendered.append(f"[{platform}]({url})" if url else platform)
        if len(rendered) >= 3:
            break
    return ", ".join(rendered) if rendered else "unknown"


def _render_trends(events: list[EnrichedEvent], trend_summary: str | None = None) -> list[str]:
    selected = [event for event in events if event.should_include_report and event.report_section != "watchlist"]
    lines = ["## \u56db\u3001\u4eca\u65e5\u8d8b\u52bf\u89c2\u5bdf", ""]
    if trend_summary:
        lines.extend([trend_summary.strip(), ""])
        return lines
    if not selected:
        lines.extend(["\u4eca\u65e5\u5165\u9009\u5185\u5bb9\u4e0d\u8db3\uff0c\u6682\u4e0d\u751f\u6210\u8d8b\u52bf\u89c2\u5bdf\u3002", ""])
        return lines

    top_events = _sort_for_section(selected, "top_news")[:3]
    topic_counter = Counter(event.normalized_event_type for event in selected)
    section_counter = Counter(event.report_section or "" for event in selected)
    topic_text = _topic_summary(topic_counter)
    examples = _trend_example_titles(top_events)
    research_count = section_counter.get("insight", 0) + section_counter.get("deep_asset", 0)

    paragraph = (
        f"\u4eca\u65e5\u5165\u9009\u5185\u5bb9\u4ee5 {topic_text} \u4e3a\u4e3b\u3002{examples} \u7b49\u6761\u76ee\u5171\u540c\u53cd\u6620\u51fa\u5f53\u5929\u6700\u503c\u5f97\u8ddf\u8e2a\u7684\u65b9\u5411\uff1b"
        f"\u5176\u4e2d\u6709 {research_count} \u6761\u6765\u81ea\u7814\u7a76\u3001\u8bc4\u6d4b\u3001\u8bba\u6587\u6216\u957f\u671f\u8d44\u6e90\u5c42\uff0c\u540e\u7eed\u5e94\u7ed3\u5408\u65b0\u589e\u7ed3\u679c\u548c\u5b9e\u9645\u843d\u5730\u60c5\u51b5\u6301\u7eed\u5224\u65ad\u5176\u5f71\u54cd\u3002"
    )
    lines.extend([paragraph, ""])
    return lines


def _topic_summary(counter: Counter[str]) -> str:
    labels = {
        "infrastructure": "\u57fa\u7840\u8bbe\u65bd",
        "hardware": "\u786c\u4ef6\u4e0e\u82af\u7247",
        "benchmark": "\u8bc4\u6d4b\u57fa\u51c6",
        "research": "\u7814\u7a76\u65b9\u6cd5",
        "open_source": "\u5f00\u6e90\u8d44\u6e90",
        "product": "\u4ea7\u54c1\u5de5\u5177",
        "product_release": "\u4ea7\u54c1\u53d1\u5e03",
        "model_release": "\u6a21\u578b\u53d1\u5e03",
        "partnership": "\u4ea7\u4e1a\u5408\u4f5c",
        "policy": "\u653f\u7b56\u6cbb\u7406",
        "funding": "\u8d44\u672c\u4e0e\u4e0a\u5e02",
    }
    parts = []
    for topic, count in counter.most_common(4):
        if not topic:
            continue
        parts.append(f"{labels.get(topic, topic)} {count} \u6761")
    return "\u3001".join(parts) if parts else "\u591a\u7c7b AI \u52a8\u6001"


def _trend_example_titles(events: list[EnrichedEvent]) -> str:
    titles = [event.title for event in events if event.title][:3]
    if not titles:
        return "\u591a\u6761\u9ad8\u5206\u4e8b\u4ef6"
    return "\u3001".join(f"\u201c{title}\u201d" for title in titles)


def _has_focus(event: EnrichedEvent, words: set[str]) -> bool:
    text = f"{event.title} {event.one_sentence} {event.why_important} {event.normalized_event_type} {' '.join(event.entities)} {' '.join(event.platforms)}".lower()
    return any(word in text for word in words)


def _trend_examples(events: list[EnrichedEvent]) -> str:
    examples = _sort_for_section(events, "top_news")[:2]
    titles = [event.title for event in examples if event.title]
    if not titles:
        return "\u9ad8\u5206\u5019\u9009\u4e8b\u4ef6"
    return "\u3001".join(f"\u201c{title}\u201d" for title in titles)

def _status_label(status: str) -> str:
    return {"verified": "\u5df2\u6838\u9a8c", "single_source": "\u5355\u6e90\u53ef\u4fe1", "rumor": "\u5f85\u89c2\u5bdf", "needs_review": "\u9700\u4eba\u5de5\u590d\u6838"}.get(status, status)


def _evidence_label(event: EnrichedEvent) -> str:
    summary = event.evidence_summary or {}
    strength = str(summary.get("evidence_strength") or "")
    count = int(summary.get("fetched_source_count") or 0)
    label = {"strong": "\u8f83\u5f3a", "medium": "\u4e2d\u7b49", "weak": "\u504f\u5f31", "none": "\u6682\u65e0"}.get(strength, strength or "\u672a\u77e5")
    if count:
        return f"{label}\uff08\u5df2\u8bfb\u53d6 {count} \u4e2a\u539f\u59cb\u6765\u6e90\uff09"
    return label

def _watch_reason(event: EnrichedEvent) -> str:
    if event.verify_status == "rumor" or "community_only" in event.report_tags:
        return "\u6765\u6e90\u66f4\u504f\u7ebf\u7d22\u6216\u793e\u533a\u4f20\u64ad\uff0c\u4fe1\u53f7\u6709\u4ef7\u503c\uff0c\u4f46\u6682\u4e0d\u5b9c\u653e\u5165\u91cd\u70b9\u65b0\u95fb\u3002"
    if _has_focus(event, COMPUTE_FOCUS_WORDS):
        return "\u7b97\u529b\u6216\u82af\u7247\u65b9\u5411\u7684\u4fe1\u53f7\u4ef7\u503c\u8f83\u9ad8\uff0c\u4f46\u8fd8\u9700\u89c2\u5bdf\u540e\u7eed\u4ea7\u54c1\u843d\u5730\u3001\u8ba2\u5355\u6216\u5b9e\u9645\u6027\u80fd\u6570\u636e\u3002"
    if _has_focus(event, BIOMED_FOCUS_WORDS):
        return "\u751f\u7269\u533b\u836f\u4ea4\u53c9\u65b9\u5411\u503c\u5f97\u8ddf\u8e2a\uff0c\u4f46\u9700\u7ee7\u7eed\u89c2\u5bdf\u8bc4\u4f30\u7ed3\u679c\u3001\u5b9e\u9a8c\u9a8c\u8bc1\u6216\u836f\u7814\u573a\u666f\u91c7\u7528\u3002"
    if event.normalized_event_type in POLICY_TYPES:
        return "\u653f\u7b56\u6216\u6cbb\u7406\u65b9\u5411\u53ef\u80fd\u5f71\u54cd\u5408\u89c4\u548c\u51fa\u6d77\uff0c\u4f46\u843d\u5730\u8def\u5f84\u548c\u6267\u884c\u7ec6\u5219\u8fd8\u9700\u7ee7\u7eed\u89c2\u5bdf\u3002"
    return "\u4e8b\u4ef6\u5177\u6709\u8ddf\u8e2a\u4ef7\u503c\uff0c\u4f46\u5f53\u524d\u66f4\u9002\u5408\u4f5c\u4e3a\u9ad8\u8d28\u91cf\u7ebf\u7d22\uff0c\u7b49\u5f85\u66f4\u660e\u786e\u7684\u843d\u5730\u8fdb\u5c55\u6216\u5916\u90e8\u9a8c\u8bc1\u3002"
