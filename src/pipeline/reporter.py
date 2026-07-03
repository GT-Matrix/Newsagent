from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from src.config import REPORT_LIMITS
from modnews.service.report.models import EnrichedEvent, ReportSection

POLICY_TYPES = {"policy", "legal", "company_policy"}
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
ASSET_TYPES = {"open_source", "tooling", "framework", "library", "paper", "benchmark", "research"}
ASSET_WORDS = {
    "github", "repo", "repository", "open source", "opensource", "framework", "toolkit", "sdk", "library",
    "benchmark", "dataset", "paper", "arxiv", "model card", "readme",
    "\u5f00\u6e90", "\u4ed3\u5e93", "\u6846\u67b6", "\u5de5\u5177", "\u6570\u636e\u96c6", "\u8bba\u6587", "\u57fa\u51c6",
}
WATCH_TYPES = {"rumor", "company_business", "company_policy", "funding", "partnership", "product_release", "model_release"}


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
    insights = _sort_for_section(
        [
            event
            for event in public_events
            if event.content_layer == "insight"
            and event.verify_status in {"verified", "single_source"}
            and event.final_score >= 60
            and event.risk_penalty <= 18
        ],
        "insight",
    )
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
    watchlist = _sort_for_section(
        [event for event in public_events if _is_watchlist_candidate(event)],
        "watchlist",
    )

    selected_top = _select_top_news(top_candidates, REPORT_LIMITS.top_news_max)
    selected_ids = {event.event_id for event in selected_top}
    selected_insights = _dedupe_section(insights, selected_ids, REPORT_LIMITS.insight_max)
    selected_ids.update(event.event_id for event in selected_insights)
    selected_assets = _dedupe_section(deep_assets, selected_ids, REPORT_LIMITS.deep_asset_max)
    selected_ids.update(event.event_id for event in selected_assets)
    selected_watch = _dedupe_section(watchlist, selected_ids, REPORT_LIMITS.watchlist_max)

    _mark(selected_top, "top_news", "\u8fbe\u5230\u91cd\u70b9\u65b0\u95fb\u9608\u503c\uff0c\u5e76\u901a\u8fc7\u7c7b\u578b\u3001\u5b9e\u4f53\u548c\u6765\u6e90\u591a\u6837\u6027\u63a7\u5236\u3002")
    _mark(selected_insights, "insight", "\u8fbe\u5230\u7814\u7a76\u3001\u8bc4\u6d4b\u6216\u65b9\u6cd5\u8bba\u5185\u5bb9\u5165\u9009\u9608\u503c\u3002")
    _mark(selected_assets, "deep_asset", "\u5177\u5907\u957f\u671f\u6c89\u6dc0\u4ef7\u503c\uff0c\u4e14\u6709\u8d44\u6e90\u8bc1\u636e\u6216\u8f83\u5f3a\u53ef\u884c\u52a8\u6027\u3002")
    _mark(selected_watch, "watchlist", "\u91cd\u8981\u4f46\u6838\u9a8c\u6216\u6765\u6e90\u5f3a\u5ea6\u4e0d\u8db3\uff0c\u8fdb\u5165\u5f85\u89c2\u5bdf\u7ebf\u7d22\u3002")
    return events


def build_report_markdown(events: list[EnrichedEvent], report_date: date) -> str:
    sections = _report_sections(events)
    lines: list[str] = [f"# AI \u60c5\u62a5\u65e9\u62a5 - {report_date.isoformat()}", ""]
    lines.extend(_render_event_section("\u4e00\u3001\u4eca\u65e5\u91cd\u70b9\u65b0\u95fb", sections["top_news"]))
    lines.extend(_render_event_section("\u4e8c\u3001\u7814\u7a76\u4e0e\u8bc4\u6d4b", sections["insight"]))
    lines.extend(_render_event_section("\u4e09\u3001\u957f\u671f\u503c\u5f97\u6c89\u6dc0", sections["deep_asset"], empty="\u4eca\u65e5\u6682\u65e0\u8fbe\u5230\u63a8\u9001\u9608\u503c\u7684\u6df1\u5c42\u8d44\u6e90\u3002"))
    lines.extend(_render_trends(events))
    lines.extend(_render_event_section("\u4e94\u3001\u9ad8\u8d28\u91cf\u5f85\u89c2\u5bdf", sections["watchlist"], empty="\u4eca\u65e5\u6682\u65e0\u9ad8\u8d28\u91cf\u5f85\u89c2\u5bdf\u5185\u5bb9\u3002"))
    lines.append("")
    lines.append("> \u8bf4\u660e\uff1a\u672c\u62a5\u544a\u9762\u5411\u7fa4\u5185\u9605\u8bfb\uff1b\u8bc4\u5206\u3001\u680f\u76ee\u5206\u548c\u6807\u7b7e\u7b49\u8c03\u8bd5\u4fe1\u606f\u5df2\u5355\u72ec\u5199\u5165 daily_report_debug.md \u548c report_candidates.json\u3002")
    return "\n".join(lines).strip() + "\n"


def build_debug_report_markdown(events: list[EnrichedEvent], report_date: date) -> str:
    sections = _report_sections(events)
    lines: list[str] = [f"# AI \u60c5\u62a5\u65e9\u62a5\u8c03\u8bd5\u7248 - {report_date.isoformat()}", ""]
    lines.extend(_render_event_section("\u4e00\u3001\u4eca\u65e5\u91cd\u70b9\u65b0\u95fb", sections["top_news"], debug=True))
    lines.extend(_render_event_section("\u4e8c\u3001\u7814\u7a76\u4e0e\u8bc4\u6d4b", sections["insight"], debug=True))
    lines.extend(_render_event_section("\u4e09\u3001\u957f\u671f\u503c\u5f97\u6c89\u6dc0", sections["deep_asset"], debug=True))
    lines.extend(_render_trends(events))
    lines.extend(_render_event_section("\u4e94\u3001\u9ad8\u8d28\u91cf\u5f85\u89c2\u5bdf", sections["watchlist"], debug=True))
    return "\n".join(lines).strip() + "\n"


def _report_sections(events: list[EnrichedEvent]) -> dict[str, list[EnrichedEvent]]:
    return {
        "top_news": [event for event in events if event.report_section == "top_news"],
        "insight": [event for event in events if event.report_section == "insight"],
        "deep_asset": [event for event in events if event.report_section == "deep_asset"],
        "watchlist": [event for event in events if event.report_section == "watchlist"],
    }

def report_candidates_payload(events: list[EnrichedEvent]) -> dict[str, list[dict[str, object]]]:
    payload: dict[str, list[dict[str, object]]] = {"top_news": [], "insight": [], "deep_asset": [], "watchlist": []}
    for section in payload:
        payload[section] = [event.to_dict() for event in events if event.report_section == section]
    return payload


def review_candidates_payload(events: list[EnrichedEvent]) -> list[dict[str, object]]:
    return [event.to_dict() for event in events if event.verify_status == "needs_review" or "source_items_missing" in event.warnings]


def _section_scores(event: EnrichedEvent) -> dict[str, float]:
    strategic_bonus = _strategic_section_bonus(event)
    top_news = event.importance_score * 0.36 + event.source_score * 0.24 + event.freshness_score * 0.22 + event.relevance_score * 0.10 + event.novelty_score * 0.08 - event.risk_penalty * 0.60 + strategic_bonus
    insight = event.novelty_score * 0.30 + event.relevance_score * 0.24 + event.source_score * 0.18 + event.importance_score * 0.16 + event.freshness_score * 0.12 - event.risk_penalty * 0.45 + strategic_bonus * 0.80
    deep_asset = event.actionability_score * 0.34 + event.novelty_score * 0.24 + event.source_score * 0.18 + event.relevance_score * 0.14 + event.importance_score * 0.10 - event.risk_penalty * 0.35 + strategic_bonus * 0.65
    watchlist = event.importance_score * 0.34 + event.novelty_score * 0.18 + event.actionability_score * 0.16 + event.freshness_score * 0.14 + event.relevance_score * 0.10 + min(event.risk_penalty, 24.0) * 0.08 - max(event.risk_penalty - 24.0, 0.0) * 0.50 + strategic_bonus * 0.90
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
    if event.verify_status == "verified" and event.final_score >= 72:
        return True
    if event.verify_status == "single_source" and event.final_score >= 82 and event.source_score >= 66:
        return True
    return False


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
        if main_platform and platform_counts[main_platform] >= 3:
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


def _dedupe_section(events: list[EnrichedEvent], excluded_ids: set[str], limit: int) -> list[EnrichedEvent]:
    selected: list[EnrichedEvent] = []
    seen_entities: set[str] = set()
    for event in events:
        if event.event_id in excluded_ids:
            continue
        entity = _main_entity(event)
        if entity and entity in seen_entities:
            continue
        selected.append(event)
        if entity:
            seen_entities.add(entity)
        if len(selected) >= limit:
            break
    return selected


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
    has_asset_type = event.normalized_event_type in ASSET_TYPES or event.content_layer in {"insight", "deep_asset"}
    has_asset_word = any(word in text for word in ASSET_WORDS)
    has_link = any(str(source.get("url") or "").strip() for source in event.source_items)
    high_utility = event.actionability_score >= 70 or event.novelty_score >= 72
    return has_asset_type and (has_asset_word or has_link) and high_utility and event.risk_penalty <= 18


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
    community_hints = {"hacker", "product", "reddit", "github", "aihot"}
    return all(any(hint in platform for hint in community_hints) for platform in platforms)


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
        status = "\u5f85\u89c2\u5bdf" if event.report_section == "watchlist" else _status_label(event.verify_status)
        evidence_label = _evidence_label(event)
        lines.append(f"{index}. **{event.title}**")
        lines.append(f"   - \u7b80\u62a5\uff1a{event.one_sentence}")
        lines.append(f"   - \u4e3a\u4ec0\u4e48\u91cd\u8981\uff1a{event.why_important}")
        if debug and event.report_section == "watchlist":
            lines.append(f"   - \u5f85\u89c2\u5bdf\u539f\u56e0\uff1a{_watch_reason(event)}")
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


def _render_trends(events: list[EnrichedEvent]) -> list[str]:
    selected = [event for event in events if event.should_include_report and event.report_section != "watchlist"]
    topic_counter = Counter(event.normalized_event_type for event in selected)
    lines = ["## \u56db\u3001\u4eca\u65e5\u8d8b\u52bf\u89c2\u5bdf", ""]
    if not selected:
        lines.extend(["\u4eca\u65e5\u5165\u9009\u5185\u5bb9\u4e0d\u8db3\uff0c\u6682\u4e0d\u751f\u6210\u8d8b\u52bf\u89c2\u5bdf\u3002", ""])
        return lines
    top_topics = [topic for topic, _ in topic_counter.most_common(3)]
    if {"infrastructure", "hardware"} & set(top_topics):
        lines.append("- \u4eca\u65e5\u4fe1\u53f7\u660e\u663e\u96c6\u4e2d\u5728\u7b97\u529b\u3001\u63a8\u7406\u548c\u57fa\u7840\u8bbe\u65bd\uff1a\u591a\u6761\u5165\u9009\u5185\u5bb9\u90fd\u6307\u5411\u90e8\u7f72\u6210\u672c\u3001\u4f9b\u7ed9\u80fd\u529b\u548c\u5de5\u7a0b\u6548\u7387\u3002")
    if "partnership" in top_topics:
        lines.append("- \u4ea7\u4e1a\u5408\u4f5c\u4ecd\u662f\u4e3b\u7ebf\uff1a\u5927\u6a21\u578b\u516c\u53f8\u3001\u786c\u4ef6\u5382\u5546\u548c\u4f01\u4e1a\u5ba2\u6237\u6b63\u5728\u628a AI \u80fd\u529b\u5f80\u66f4\u5177\u4f53\u7684\u843d\u5730\u573a\u666f\u63a8\u8fdb\u3002")
    if {"research", "benchmark", "open_source"} & set(top_topics):
        lines.append("- \u7814\u7a76\u3001\u57fa\u51c6\u548c\u5f00\u6e90\u5185\u5bb9\u9002\u5408\u8fdb\u5165\u957f\u671f\u8ddf\u8e2a\uff1a\u5b83\u4eec\u672a\u5fc5\u7acb\u523b\u5f71\u54cd\u4ea7\u54c1\uff0c\u4f46\u6709\u52a9\u4e8e\u5224\u65ad\u6280\u672f\u8def\u7ebf\u548c\u80fd\u529b\u8fb9\u754c\u3002")
    if not lines[-1].startswith("-"):
        topic_text = "\u3001".join(top_topics)
        lines.append(f"- \u4eca\u65e5\u4e3b\u8981\u4fe1\u53f7\u96c6\u4e2d\u5728 {topic_text}\uff0c\u5efa\u8bae\u7ed3\u5408\u539f\u59cb\u94fe\u63a5\u7ee7\u7eed\u8ddf\u8fdb\u5176\u771f\u5b9e\u5f71\u54cd\u3002")
    lines.append("")
    return lines

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
    return "\u4fe1\u53f7\u4ef7\u503c\u8f83\u9ad8\uff0c\u4f46\u66f4\u9002\u5408\u4f5c\u4e3a\u540e\u7eed\u8ddf\u8e2a\u9879\uff0c\u5efa\u8bae\u5173\u6ce8\u5b98\u65b9\u786e\u8ba4\u3001\u66f4\u591a\u4ea4\u53c9\u62a5\u9053\u6216\u5b9e\u9645\u843d\u5730\u8fdb\u5c55\u3002"
