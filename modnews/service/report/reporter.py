from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from modnews.service.report.config import REPORT_LIMITS
from modnews.service.report.models import EnrichedEvent, ReportSection

POLICY_TYPES = {"policy", "legal", "company_policy"}
PAPER_PLATFORMS = {"arxiv", "huggingface_papers_trending"}
PAPER_TYPES = {"research", "benchmark", "paper"}
PAPER_WORDS = {
    "paper", "arxiv", "benchmark", "dataset", "research", "method", "architecture",
    "论文", "基准", "数据集", "研究", "方法", "架构",
}
REUSABLE_ASSET_WORDS = {
    "github", "repo", "repository", "open source", "opensource", "framework", "toolkit", "sdk",
    "library", "dataset", "benchmark", "code", "agent", "memory", "retrieval", "ocr",
    "开源", "仓库", "框架", "工具", "数据集", "基准", "代码", "智能体", "记忆", "检索",
}
COMPUTE_FOCUS_WORDS = {
    "chip", "gpu", "hbm", "blackwell", "rubin", "jetson", "inference", "compute", "datacenter",
    "data center", "accelerator", "semiconductor", "nvidia", "broadcom", "tsmc",
    "芯片", "算力", "推理", "半导体", "数据中心", "英伟达", "存储", "晶圆",
}
BIOMED_FOCUS_WORDS = {
    "biology", "biomedical", "medicine", "drug", "pharma", "life science", "protein", "genomics",
    "clinical", "molecule", "chemistry", "bionemo", "gene",
    "生物", "生物医药", "医药", "生命科学", "药物", "制药", "蛋白", "基因", "临床", "分子", "化学",
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
DEEP_ASSET_EXCLUDE = {"course", "academy", "education", "课程", "教育"}
ASSET_TYPES = {"open_source", "tooling", "framework", "library", "paper", "benchmark", "research"}
ASSET_WORDS = {
    "github", "repo", "repository", "open source", "opensource", "framework", "toolkit", "sdk", "library",
    "benchmark", "dataset", "paper", "arxiv", "model card", "readme",
    "开源", "仓库", "框架", "工具", "数据集", "论文", "基准",
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
    watchlist = _sort_for_section([event for event in public_events if _is_watchlist_candidate(event)], "watchlist")

    selected_top = _select_top_news(top_candidates, REPORT_LIMITS.top_news_max)
    selected_ids = {event.event_id for event in selected_top}
    selected_insights = _select_research_section(insights, selected_ids, REPORT_LIMITS.insight_max)
    selected_ids.update(event.event_id for event in selected_insights)
    selected_assets = _select_asset_section(deep_assets, selected_ids, REPORT_LIMITS.deep_asset_max)
    selected_ids.update(event.event_id for event in selected_assets)
    selected_watch = _dedupe_section(watchlist, selected_ids, REPORT_LIMITS.watchlist_max)

    _mark(selected_top, "top_news", "达到重点新闻阈值，并通过类型、实体和来源多样性控制。")
    _mark(selected_insights, "insight", "达到研究、评测或论文信号入选阈值。")
    _mark(selected_assets, "deep_asset", "具备长期方法、工具或技术资产沉淀价值。")
    _mark(selected_watch, "watchlist", "重要但核验或来源强度不足，进入待观察线索。")
    return events


def build_report_markdown(events: list[EnrichedEvent], report_date: date, trend_summary: str | None = None) -> str:
    sections = _report_sections(events)
    lines: list[str] = [f"# AI 情报早报 - {report_date.isoformat()}", ""]
    lines.extend(_render_event_section("一、今日重点新闻", sections["top_news"]))
    lines.extend(_render_event_section("二、研究、评测与论文", sections["insight"]))
    lines.extend(_render_event_section("三、长期方法与资源沉淀", sections["deep_asset"], empty="今日暂无达到推送阈值的深层资源。"))
    lines.extend(_render_trends(events, trend_summary))
    lines.extend(_render_event_section("五、高质量待观察", sections["watchlist"], empty="今日暂无高质量待观察内容。"))
    lines.append("")
    lines.append("> 说明：本报告面向群内阅读；评分、栏目分和标签等调试信息已单独写入 daily_report_debug.md 和 report_candidates.json。")
    return "\n".join(lines).strip() + "\n"


def build_debug_report_markdown(events: list[EnrichedEvent], report_date: date, trend_summary: str | None = None) -> str:
    sections = _report_sections(events)
    lines: list[str] = [f"# AI 情报早报调试版 - {report_date.isoformat()}", ""]
    lines.extend(_render_event_section("一、今日重点新闻", sections["top_news"], debug=True))
    lines.extend(_render_event_section("二、研究、评测与论文", sections["insight"], debug=True))
    lines.extend(_render_event_section("三、长期方法与资源沉淀", sections["deep_asset"], debug=True))
    lines.extend(_render_trends(events, trend_summary))
    lines.extend(_render_event_section("五、高质量待观察", sections["watchlist"], debug=True))
    return "\n".join(lines).strip() + "\n"


def _report_sections(events: list[EnrichedEvent]) -> dict[str, list[EnrichedEvent]]:
    return {
        "top_news": [event for event in events if event.report_section == "top_news"],
        "insight": [event for event in events if event.report_section == "insight"],
        "deep_asset": [event for event in events if event.report_section == "deep_asset"],
        "watchlist": [event for event in events if event.report_section == "watchlist"],
    }


def report_candidates_payload(events: list[EnrichedEvent]) -> dict[str, list[dict[str, object]]]:
    payload: dict[str, list[dict[str, object]]] = {"top_news": [], "insight": [], "deep_asset": [], "watchlist": [], "unselected_high_score": []}
    for section in ("top_news", "insight", "deep_asset", "watchlist"):
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
    strategic_bonus = _strategic_section_bonus(event)
    paper_bonus = 6.0 if _is_paper_event(event) else 0.0
    asset_bonus = 5.0 if _has_reusable_asset_signal(event) else 0.0
    top_news = event.importance_score * 0.40 + event.source_score * 0.14 + event.freshness_score * 0.22 + event.relevance_score * 0.14 + event.novelty_score * 0.10 - event.risk_penalty * 0.45 + strategic_bonus
    insight = event.novelty_score * 0.32 + event.relevance_score * 0.28 + event.source_score * 0.10 + event.importance_score * 0.18 + event.freshness_score * 0.12 - event.risk_penalty * 0.35 + strategic_bonus * 0.80 + paper_bonus
    deep_asset = event.actionability_score * 0.38 + event.novelty_score * 0.26 + event.source_score * 0.10 + event.relevance_score * 0.16 + event.importance_score * 0.10 - event.risk_penalty * 0.30 + strategic_bonus * 0.65 + asset_bonus
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
    if event.verify_status == "rumor":
        return False
    return event.final_score >= 72 and event.risk_penalty <= 18


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


def _select_research_section(events: list[EnrichedEvent], excluded_ids: set[str], limit: int) -> list[EnrichedEvent]:
    eligible = [event for event in events if event.event_id not in excluded_ids]
    selected = _dedupe_section(eligible, set(), limit)
    paper_candidates = [event for event in eligible if _is_paper_event(event) and event.section_scores.get("insight", 0.0) >= 58]
    trending_papers = [event for event in eligible if _is_trending_paper_event(event) and event.section_scores.get("insight", 0.0) >= 58]
    if paper_candidates and not any(_is_paper_event(event) for event in selected):
        selected = _force_include_candidate(selected, paper_candidates[0], limit, section="insight")
    if trending_papers and not any(_is_trending_paper_event(event) for event in selected):
        selected = _force_include_candidate(selected, trending_papers[0], limit, section="insight")
    return _sort_for_section(_dedupe_keep_order(selected), "insight")[:limit]


def _select_asset_section(events: list[EnrichedEvent], excluded_ids: set[str], limit: int) -> list[EnrichedEvent]:
    eligible = [event for event in events if event.event_id not in excluded_ids]
    selected = _dedupe_section(eligible, set(), limit)
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
    has_asset_type = event.normalized_event_type in ASSET_TYPES or event.content_layer in {"insight", "deep_asset"}
    has_asset_word = any(word in text for word in ASSET_WORDS) or _has_reusable_asset_signal(event)
    has_link = any(str(source.get("url") or "").strip() for source in event.source_items)
    high_utility = event.actionability_score >= 70 or event.novelty_score >= 72 or (_is_paper_event(event) and event.final_score >= 52)
    return has_asset_type and (has_asset_word or has_link) and high_utility and event.risk_penalty <= 18


def _is_research_insight_candidate(event: EnrichedEvent) -> bool:
    if event.verify_status not in {"verified", "single_source"} or event.risk_penalty > 18:
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
    community_hints = {"linux_do", "hacker", "product", "reddit", "github", "aihot"}
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
    empty: str = "今日暂无达标内容。",
    *,
    debug: bool = False,
) -> list[str]:
    lines = [f"## {title}", ""]
    if not events:
        lines.extend([empty, ""])
        return lines
    for index, event in enumerate(events, start=1):
        sources = _render_sources(event)
        status = "待观察" if event.report_section == "watchlist" else _status_label(event.verify_status)
        evidence_label = _evidence_label(event)
        lines.append(f"{index}. **{event.title}**")
        lines.append(f"   - 简报：{event.one_sentence}")
        lines.append(f"   - 为什么重要：{event.why_important}")
        if debug and event.report_section == "watchlist":
            lines.append(f"   - 待观察原因：{_watch_reason(event)}")
        lines.append(f"   - 来源：{sources}")
        if debug:
            lines.append(f"   - 状态：{status}；证据：{evidence_label}")
            tags = "、".join(event.report_tags[:8])
            section_score = event.section_scores.get(event.report_section or "", event.final_score)
            lines.append(f"   - Debug：总分 {event.final_score:.1f}；栏目分 {section_score:.1f}；类型 {event.normalized_event_type}；标签 {tags}")
            if event.warnings:
                lines.append(f"   - Warnings：{', '.join(event.warnings[:5])}")
        else:
            lines.append(f"   - 状态：{status}")
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
    lines = ["## 四、今日趋势观察", ""]
    if trend_summary:
        lines.extend([trend_summary.strip(), ""])
        return lines
    if not selected:
        lines.extend(["今日入选内容不足，暂不生成趋势观察。", ""])
        return lines

    top_events = _sort_for_section(selected, "top_news")[:3]
    topic_counter = Counter(event.normalized_event_type for event in selected)
    section_counter = Counter(event.report_section or "" for event in selected)
    topic_text = _topic_summary(topic_counter)
    examples = _trend_example_titles(top_events)
    research_count = section_counter.get("insight", 0) + section_counter.get("deep_asset", 0)

    paragraph = (
        f"今天入选内容整体呈现出从产业基础设施到方法沉淀同步推进的特征：{examples} 等事件说明，"
        f"市场关注点正在从单点模型能力扩展到算力供给、部署成本、企业落地和可复用技术资产。"
        f"从类型分布看，今天更集中的信号包括：{topic_text}；同时有 {research_count} 条内容来自研究、评测、论文或长期资源层，"
        "说明值得跟踪的不只是即时新闻，也包括后续可能影响产品路线和工程实践的方法类成果。"
    )
    lines.extend([paragraph, ""])
    return lines


def _topic_summary(counter: Counter[str]) -> str:
    labels = {
        "infrastructure": "基础设施",
        "hardware": "硬件与芯片",
        "benchmark": "评测基准",
        "research": "研究方法",
        "open_source": "开源资源",
        "product": "产品工具",
        "product_release": "产品发布",
        "model_release": "模型发布",
        "partnership": "产业合作",
        "policy": "政策治理",
        "funding": "资本与上市",
    }
    parts = []
    for topic, count in counter.most_common(4):
        if not topic:
            continue
        parts.append(f"{labels.get(topic, topic)} {count} 条")
    return "、".join(parts) if parts else "多类 AI 动态"


def _trend_example_titles(events: list[EnrichedEvent]) -> str:
    titles = [event.title for event in events if event.title][:3]
    if not titles:
        return "多条高分事件"
    return "、".join(f"“{title}”" for title in titles)


def _has_focus(event: EnrichedEvent, words: set[str]) -> bool:
    text = f"{event.title} {event.one_sentence} {event.why_important} {event.normalized_event_type} {' '.join(event.entities)} {' '.join(event.platforms)}".lower()
    return any(word in text for word in words)


def _status_label(status: str) -> str:
    return {"verified": "已核验", "single_source": "单源可信", "rumor": "待观察", "needs_review": "需人工复核"}.get(status, status)


def _evidence_label(event: EnrichedEvent) -> str:
    summary = event.evidence_summary or {}
    strength = str(summary.get("evidence_strength") or "")
    count = int(summary.get("fetched_source_count") or 0)
    label = {"strong": "较强", "medium": "中等", "weak": "偏弱", "none": "暂无"}.get(strength, strength or "未知")
    if count:
        return f"{label}（已读取 {count} 个原始来源）"
    return label


def _watch_reason(event: EnrichedEvent) -> str:
    if event.verify_status == "rumor" or "community_only" in event.report_tags:
        return "来源更偏线索或社区传播，信号有价值，但暂不宜放入重点新闻。"
    if _has_focus(event, COMPUTE_FOCUS_WORDS):
        return "算力或芯片方向的信号价值较高，但还需观察后续产品落地、订单或实际性能数据。"
    if _has_focus(event, BIOMED_FOCUS_WORDS):
        return "生物医药交叉方向值得跟踪，但需继续观察评估结果、实验验证或药研场景采用。"
    if event.normalized_event_type in POLICY_TYPES:
        return "政策或治理方向可能影响合规和出海，但落地路径和执行细则还需继续观察。"
    return "事件具有跟踪价值，但当前更适合作为高质量线索，等待更明确的落地进展或外部验证。"
