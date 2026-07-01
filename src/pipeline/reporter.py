from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from src.config import REPORT_LIMITS
from src.models import EnrichedEvent, ReportSection

POLICY_TYPES = {"policy", "legal", "company_policy"}
DEEP_ASSET_EXCLUDE = {"course", "academy", "education", "\u8bfe\u7a0b", "\u6559\u80b2"}


def assign_report_sections(events: list[EnrichedEvent]) -> list[EnrichedEvent]:
    for event in events:
        event.should_include_report = False
        event.report_section = None
        event.report_reason = ""

    verified_news = [
        event
        for event in events
        if event.content_layer == "news"
        and event.verify_status == "verified"
        and event.final_score >= 72
    ]
    single_source_news = [
        event
        for event in events
        if event.content_layer == "news"
        and event.verify_status == "single_source"
        and event.final_score >= 80
    ]
    insights = [
        event
        for event in events
        if event.content_layer == "insight"
        and event.verify_status in {"verified", "single_source"}
        and event.final_score >= 58
    ]
    deep_assets = [
        event
        for event in events
        if event.content_layer == "deep_asset"
        and event.verify_status in {"verified", "single_source"}
        and event.final_score >= 58
        and _is_real_deep_asset(event)
    ]
    watchlist = [
        event
        for event in events
        if event.verify_status == "rumor" and event.importance_score >= 55
    ]

    selected_top = _select_top_news([*verified_news, *single_source_news], REPORT_LIMITS.top_news_max)
    _mark(selected_top, "top_news", "达到重点新闻入选阈值。")
    _mark(insights[: REPORT_LIMITS.insight_max], "insight", "达到中层 know-how / 研究内容入选阈值。")
    _mark(deep_assets[: REPORT_LIMITS.deep_asset_max], "deep_asset", "达到长期沉淀资源入选阈值。")
    _mark(watchlist[: REPORT_LIMITS.watchlist_max], "watchlist", "重要但未充分核验，进入待观察线索。")
    return events


def build_report_markdown(events: list[EnrichedEvent], report_date: date) -> str:
    sections = {
        "top_news": [event for event in events if event.report_section == "top_news"],
        "insight": [event for event in events if event.report_section == "insight"],
        "deep_asset": [event for event in events if event.report_section == "deep_asset"],
        "watchlist": [event for event in events if event.report_section == "watchlist"],
    }

    lines: list[str] = [f"# AI 情报早报 - {report_date.isoformat()}", ""]
    lines.extend(_render_event_section("一、今日重点新闻", sections["top_news"]))
    lines.extend(_render_event_section("二、行业 know-how / 优秀论文", sections["insight"]))
    lines.extend(_render_event_section("三、长期值得沉淀", sections["deep_asset"], empty="今日暂无达到推送阈值的深层资源。"))
    lines.extend(_render_trends(events))
    lines.extend(_render_event_section("五、待观察线索", sections["watchlist"], empty="今日暂无高优先级待观察线索。"))
    lines.append("")
    lines.append("> 说明：本报告面向群内推送；需人工复核的疑似错聚类内容已移出正文，写入 review_candidates.json。")
    return "\n".join(lines).strip() + "\n"


def report_candidates_payload(events: list[EnrichedEvent]) -> dict[str, list[dict[str, object]]]:
    payload: dict[str, list[dict[str, object]]] = {
        "top_news": [],
        "insight": [],
        "deep_asset": [],
        "watchlist": [],
    }
    for section in payload:
        payload[section] = [event.to_dict() for event in events if event.report_section == section]
    return payload


def review_candidates_payload(events: list[EnrichedEvent]) -> list[dict[str, object]]:
    return [
        event.to_dict()
        for event in events
        if event.verify_status == "needs_review" or "source_items_missing" in event.warnings
    ]


def _select_top_news(events: list[EnrichedEvent], limit: int) -> list[EnrichedEvent]:
    selected: list[EnrichedEvent] = []
    seen: set[str] = set()
    type_counts: defaultdict[str, int] = defaultdict(int)
    for event in events:
        if event.event_id in seen:
            continue
        if event.normalized_event_type in POLICY_TYPES and type_counts["policy"] >= 2:
            continue
        selected.append(event)
        seen.add(event.event_id)
        if event.normalized_event_type in POLICY_TYPES:
            type_counts["policy"] += 1
        if len(selected) >= limit:
            break
    return selected


def _is_real_deep_asset(event: EnrichedEvent) -> bool:
    text = f"{event.title} {event.one_sentence} {event.normalized_event_type}".lower()
    if any(word in text for word in DEEP_ASSET_EXCLUDE):
        return False
    allow_words = {
        "open", "source", "github", "repo", "framework", "tool", "sdk", "library",
        "benchmark", "dataset", "paper", "model", "\u5f00\u6e90", "\u6846\u67b6", "\u5de5\u5177", "\u8bba\u6587", "\u57fa\u51c6", "\u6a21\u578b",
    }
    return any(word in text for word in allow_words)


def _mark(events: list[EnrichedEvent], section: ReportSection, reason: str) -> None:
    for event in events:
        event.should_include_report = True
        event.report_section = section
        event.report_reason = reason


def _render_event_section(title: str, events: list[EnrichedEvent], empty: str = "今日暂无达标内容。") -> list[str]:
    lines = [f"## {title}", ""]
    if not events:
        lines.extend([empty, ""])
        return lines
    for index, event in enumerate(events, start=1):
        sources = _render_sources(event)
        status = _status_label(event.verify_status)
        lines.append(f"{index}. **{event.title}**")
        lines.append(f"   - 一句话：{event.one_sentence}")
        lines.append(f"   - 为什么重要：{event.why_important}")
        lines.append(f"   - 来源：{sources}")
        lines.append(f"   - 状态：{status}；评分：{event.final_score:.1f}")
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
    platform_counter = Counter(platform for event in selected for platform in event.platforms)
    lines = ["## 四、今日趋势观察", ""]
    if not selected:
        lines.extend(["今日入选内容不足，暂不生成趋势观察。", ""])
        return lines
    for topic, count in topic_counter.most_common(3):
        lines.append(f"- `{topic}` 相关内容出现 {count} 条，是今日主要信号之一。")
    if platform_counter:
        platform, count = platform_counter.most_common(1)[0]
        lines.append(f"- `{platform}` 是今日入选内容中出现最多的来源之一，共 {count} 条。")
    lines.append("")
    return lines


def _status_label(status: str) -> str:
    return {
        "verified": "已核验",
        "single_source": "单源可信",
        "rumor": "待观察",
        "needs_review": "需人工复核",
    }.get(status, status)