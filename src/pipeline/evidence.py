from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import requests

from src.models import EnrichedEvent

MAX_SOURCES_PER_EVENT = 2
MAX_TEXT_CHARS = 6000
REQUEST_TIMEOUT_SECONDS = 12
MAX_EVIDENCE_WORKERS = 8

OFFICIAL_DOMAINS = {
    "openai.com",
    "anthropic.com",
    "deepmind.google",
    "googleblog.com",
    "nvidia.com",
    "microsoft.com",
    "meta.com",
    "huggingface.co",
    "github.com",
    "arxiv.org",
}


@dataclass
class EvidenceItem:
    source_news_id: int | None
    platform: str
    url: str
    title: str
    fetched: bool
    http_status: int | None
    content_type: str | None
    canonical_domain: str
    text: str
    text_chars: int
    fetch_error: str | None = None


def enrich_report_evidence(events: list[EnrichedEvent], *, report_only: bool = True) -> list[dict[str, Any]]:
    selected = [event for event in events if event.should_include_report] if report_only else list(events)
    payload: list[dict[str, Any]] = []
    source_rows_by_event: dict[str, list[dict[str, Any]]] = {
        event.event_id: _select_sources(event) for event in selected
    }
    evidence_by_event: dict[str, list[EvidenceItem]] = {event.event_id: [] for event in selected}

    jobs: list[tuple[str, int, dict[str, Any]]] = []
    for event_id, rows in source_rows_by_event.items():
        for index, row in enumerate(rows):
            jobs.append((event_id, index, row))

    if jobs:
        with ThreadPoolExecutor(max_workers=MAX_EVIDENCE_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_source_for_job, event_id, index, row): (event_id, index)
                for event_id, index, row in jobs
            }
            for future in as_completed(futures):
                event_id, _ = futures[future]
                try:
                    _, _, item = future.result()
                except Exception as exc:
                    item = EvidenceItem(
                        source_news_id=None,
                        platform="unknown",
                        url="",
                        title="",
                        fetched=False,
                        http_status=None,
                        content_type=None,
                        canonical_domain="",
                        text="",
                        text_chars=0,
                        fetch_error=f"{type(exc).__name__}: {exc}",
                    )
                evidence_by_event.setdefault(event_id, []).append(item)

    for event in selected:
        evidence_items = evidence_by_event.get(event.event_id, [])
        evidence_items.sort(key=lambda item: _source_priority(item.platform, item.url))
        summary = _summarize_evidence(event, evidence_items)
        event.evidence_summary = summary
        payload.append(
            {
                "event_id": event.event_id,
                "title": event.title,
                "report_section": event.report_section,
                "evidence_items": [asdict(item) for item in evidence_items],
                "evidence_summary": summary,
            }
        )
    return payload


def apply_evidence_verification(events: list[EnrichedEvent]) -> None:
    """Set public eligibility from readable evidence, not source category."""
    for event in events:
        if event.verify_status == "rumor" or event.text_quality in {"bad", "missing"}:
            continue
        summary = event.evidence_summary or {}
        strength = str(summary.get("evidence_strength") or "none")
        fetched_count = int(summary.get("fetched_source_count") or 0)
        domains = {str(domain) for domain in (summary.get("domains") or []) if domain}
        if strength == "none" or fetched_count == 0:
            event.verify_status = "needs_review"
            event.verify_reason = "未取得可用于编报的原文内容。"
        elif len(domains) >= 2 and fetched_count >= 2:
            event.verify_status = "verified"
            event.verify_reason = "已获得两个独立来源的可读原文。"
        else:
            event.verify_status = "single_source"
            event.verify_reason = "已获得可读主原文。"


def _fetch_source_for_job(event_id: str, index: int, row: dict[str, Any]) -> tuple[str, int, EvidenceItem]:
    session = requests.Session()
    session.headers.update({"User-Agent": "newsagent-evidence/0.1"})
    return event_id, index, _fetch_source(session, row)


def _select_sources(event: EnrichedEvent) -> list[dict[str, Any]]:
    rows = [source for source in event.source_items if str(source.get("url") or "").startswith(("http://", "https://"))]
    rows.sort(key=lambda row: _source_priority(str(row.get("platform") or ""), str(row.get("url") or "")))
    seen: set[str] = set()
    selected: list[dict[str, Any]] = []
    for row in rows:
        url = str(row.get("url") or "")
        key = _canonical_url_key(url)
        if not key or key in seen:
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) >= MAX_SOURCES_PER_EVENT:
            break
    return selected


def _source_priority(platform: str, url: str) -> tuple[int, str]:
    return (0, f"{platform.lower()}|{_domain(url)}")


def _fetch_source(session: requests.Session, row: dict[str, Any]) -> EvidenceItem:
    url = str(row.get("url") or "")
    platform = str(row.get("platform") or "unknown")
    title = str(row.get("title") or "")
    source_news_id = row.get("source_news_id")
    domain = _domain(url)
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
        content_type = response.headers.get("content-type", "")
        response.raise_for_status()
        text = _extract_text(response.text, content_type)
        return EvidenceItem(
            source_news_id=source_news_id if isinstance(source_news_id, int) else None,
            platform=platform,
            url=url,
            title=title,
            fetched=True,
            http_status=response.status_code,
            content_type=content_type,
            canonical_domain=domain,
            text=text[:MAX_TEXT_CHARS],
            text_chars=len(text),
        )
    except Exception as exc:  # network and parser errors should not break report generation
        return EvidenceItem(
            source_news_id=source_news_id if isinstance(source_news_id, int) else None,
            platform=platform,
            url=url,
            title=title,
            fetched=False,
            http_status=getattr(getattr(exc, "response", None), "status_code", None),
            content_type=None,
            canonical_domain=domain,
            text="",
            text_chars=0,
            fetch_error=f"{type(exc).__name__}: {exc}",
        )


def _summarize_evidence(event: EnrichedEvent, items: list[EvidenceItem]) -> dict[str, Any]:
    fetched = [item for item in items if item.fetched and item.text]
    domains = sorted({item.canonical_domain for item in fetched if item.canonical_domain})
    source_agreement = "none"
    if len(fetched) >= 2:
        source_agreement = "multi_source"
    elif len(fetched) == 1:
        source_agreement = "single_source"

    title_tokens = _tokens(event.title)
    key_sentences: list[str] = []
    for item in fetched:
        key_sentences.extend(_extract_key_sentences(item.text, title_tokens, limit=2))

    if not fetched:
        strength = "none"
    elif len(domains) >= 2:
        strength = "strong"
    elif key_sentences:
        strength = "medium"
    else:
        strength = "weak"

    mismatch_flags: list[str] = []
    if any(not item.fetched for item in items):
        mismatch_flags.append("source_fetch_failed")

    key_facts = _dedupe(key_sentences)[:5]
    signals = _news_value_signals(event, fetched, key_facts)
    summary = {
        "canonical_claim": event.one_sentence or event.title,
        "key_facts": key_facts,
        "fact_summary": _build_fact_summary(event, key_facts),
        "news_value_signals": signals,
        "low_news_value": "low_news_value" in signals,
        "soft_commentary": "soft_commentary" in signals,
        "domains": domains,
        "source_agreement": source_agreement,
        "evidence_strength": strength,
        "mismatch_flags": mismatch_flags,
        "needs_review": strength == "none",
        "fetched_source_count": len(fetched),
        "requested_source_count": len(items),
        "duplicate_key": _duplicate_key(event),
    }
    summary["brief"] = _build_evidence_brief(event, fetched, summary)
    return summary


def _build_fact_summary(event: EnrichedEvent, key_facts: list[str]) -> str:
    if key_facts:
        clean = _normalize_text(key_facts[0])
        return clean[:360].rstrip()
    return event.one_sentence or event.title


def _news_value_signals(event: EnrichedEvent, fetched: list[EvidenceItem], key_facts: list[str]) -> list[str]:
    text = " ".join(
        [
            event.title,
            event.one_sentence,
            event.why_important,
            event.normalized_event_type,
            " ".join(event.entities),
            " ".join(item.title for item in fetched),
            " ".join(key_facts[:3]),
        ]
    ).lower()
    signals: set[str] = set()
    if event.normalized_event_type in {"model_release", "product_release", "policy", "legal", "funding", "partnership", "hardware", "infrastructure"}:
        signals.add("hard_news")
    if event.normalized_event_type in {"research", "benchmark", "paper"}:
        signals.add("research_signal")
    if event.normalized_event_type in {"open_source", "tooling", "framework", "library"}:
        signals.add("reusable_asset")
    if any(word in text for word in ["release", "released", "launch", "launched", "announce", "announced", "introduce", "introduced", "发布", "推出", "上线"]):
        signals.add("announcement")
    if any(word in text for word in ["guide", "best practice", "tutorial", "how to", "walkthrough", "case study", "reference architecture", "指南", "教程", "最佳实践", "案例", "参考架构"]):
        signals.add("low_news_value")
    if any(word in text for word in ["questions", "criticizes", "warns", "doubts", "opinion", "skeptical", "质疑", "怀疑", "警告", "批评", "观点", "担忧"]):
        signals.add("soft_commentary")
    if len({item.canonical_domain for item in fetched if item.canonical_domain}) >= 2:
        signals.add("multi_source_evidence")
    if any(_is_official_domain(item.canonical_domain) for item in fetched):
        signals.add("official_evidence")
    return sorted(signals)


def _build_evidence_brief(event: EnrichedEvent, fetched: list[EvidenceItem], summary: dict[str, Any]) -> str:
    sentences: list[str] = []
    title = _ensure_sentence(event.title)
    if fetched:
        sentences.append(f"\u539f\u6587\u56de\u6eaf\u663e\u793a\uff0c{title}")
    else:
        sentences.append(f"\u76ee\u524d\u6682\u672a\u6293\u53d6\u5230\u53ef\u7528\u539f\u6587\uff0c\u4ecd\u4ee5\u5df2\u805a\u7c7b\u6807\u9898\u5224\u65ad\uff1a{title}")

    source_line = _source_context_sentence(fetched, summary)
    if source_line:
        sentences.append(source_line)

    impact = _impact_sentence(event)
    if impact:
        sentences.append(impact)
    return "\u3002".join(sentence.rstrip("\u3002.!?") for sentence in sentences[:3] if sentence).strip() + "\u3002"


def _source_context_sentence(fetched: list[EvidenceItem], summary: dict[str, Any]) -> str:
    domains = list(summary.get("domains") or [])
    strength = _strength_label(str(summary.get("evidence_strength") or ""))
    fetched_count = int(summary.get("fetched_source_count") or 0)
    requested_count = int(summary.get("requested_source_count") or 0)
    if not fetched:
        if requested_count:
            return "\u5df2\u5c1d\u8bd5\u8bbf\u95ee\u539f\u59cb\u6765\u6e90\uff0c\u4f46\u76ee\u524d\u9875\u9762\u4e0d\u53ef\u8bfb\u6216\u6293\u53d6\u5931\u8d25\uff0c\u9700\u540e\u7eed\u4eba\u5de5\u590d\u6838"
        return ""
    domain_text = "\u3001".join(domains[:3]) if domains else "\u539f\u59cb\u7ad9\u70b9"
    if fetched_count >= 2:
        return f"\u7cfb\u7edf\u5df2\u8bfb\u53d6 {fetched_count} \u4e2a\u539f\u59cb\u6765\u6e90\uff08{domain_text}\uff09\uff0c\u76f8\u5173\u9875\u9762\u6307\u5411\u540c\u4e00\u4e8b\u4ef6\uff0c\u8bc1\u636e\u5f3a\u5ea6\u4e3a{strength}"
    return f"\u7cfb\u7edf\u5df2\u8bfb\u53d6\u539f\u59cb\u6765\u6e90\uff08{domain_text}\uff09\uff0c\u53ef\u4f5c\u4e3a\u8be5\u4e8b\u4ef6\u7684\u76f4\u63a5\u4f9d\u636e\uff0c\u8bc1\u636e\u5f3a\u5ea6\u4e3a{strength}"


def _strength_label(value: str) -> str:
    return {
        "strong": "\u8f83\u5f3a",
        "medium": "\u4e2d\u7b49",
        "weak": "\u504f\u5f31",
        "none": "\u6682\u65e0",
    }.get(value, value or "\u672a\u77e5")

def _impact_sentence(event: EnrichedEvent) -> str:
    event_type = event.normalized_event_type
    if event_type in {"policy", "legal", "company_policy"}:
        return "\u5173\u6ce8\u70b9\u5728\u4e8e\u5b83\u53ef\u80fd\u6539\u53d8 AI \u5185\u5bb9\u3001\u4ea7\u54c1\u6216\u5e73\u53f0\u7684\u5408\u89c4\u8fb9\u754c"
    if event_type in {"infrastructure", "hardware"}:
        return "\u5bf9\u56e2\u961f\u6765\u8bf4\uff0c\u8fd9\u7c7b\u4fe1\u606f\u4e3b\u8981\u5f71\u54cd\u7b97\u529b\u4f9b\u7ed9\u3001\u63a8\u7406\u6548\u7387\u548c\u90e8\u7f72\u6210\u672c\u5224\u65ad"
    if event_type in {"research", "benchmark"}:
        return "\u8fd9\u7c7b\u5185\u5bb9\u66f4\u9002\u5408\u8fdb\u5165\u65b9\u6cd5\u8bba\u548c\u6280\u672f\u8d8b\u52bf\u89c2\u5bdf\uff0c\u540e\u7eed\u53ef\u7ed3\u5408\u8bba\u6587\u6216\u57fa\u51c6\u7ed3\u679c\u7ee7\u7eed\u8ddf\u8fdb"
    if event_type in {"open_source", "tooling", "framework", "library"}:
        return "\u5b83\u7684\u4ef7\u503c\u4e3b\u8981\u5728\u4e8e\u662f\u5426\u80fd\u88ab\u56e2\u961f\u590d\u7528\u3001\u8bc4\u4f30\u6216\u7eb3\u5165\u5de5\u7a0b\u5b9e\u9a8c"
    if event_type in {"partnership", "funding", "company_business"}:
        return "\u8be5\u4e8b\u4ef6\u66f4\u591a\u4f53\u73b0\u4ea7\u4e1a\u534f\u4f5c\u3001\u5546\u4e1a\u5316\u6216\u7ade\u4e89\u683c\u5c40\u7684\u53d8\u5316"
    return "\u8fd9\u6761\u4fe1\u606f\u53ef\u4f5c\u4e3a\u4eca\u65e5 AI \u884c\u4e1a\u52a8\u6001\u7684\u6709\u6548\u7ebf\u7d22\uff0c\u9002\u5408\u8fdb\u5165\u56e2\u961f\u60c5\u62a5\u6c60"


def _ensure_sentence(text: str) -> str:
    clean = text.strip()
    if not clean:
        return "\u8be5\u4e8b\u4ef6\u7f3a\u5c11\u6807\u9898\u4fe1\u606f\u3002"
    return clean if clean.endswith(("\u3002", ".", "!", "?", "\uff01", "\uff1f")) else clean + "\u3002"

def _extract_text(raw_html: str, content_type: str) -> str:
    if "html" not in content_type.lower():
        return _normalize_text(raw_html)
    parser = _ReadableHTMLParser()
    parser.feed(raw_html)
    return _normalize_text(" ".join(parser.parts))


class _ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if len(text) >= 2:
            self.parts.append(text)


def _extract_key_sentences(text: str, tokens: set[str], limit: int) -> list[str]:
    sentences = re.split(r"(?<=[.!????])\s+", text)
    scored: list[tuple[int, str]] = []
    for sentence in sentences:
        clean = sentence.strip()
        if len(clean) < 30:
            continue
        lowered = clean.lower()
        score = sum(1 for token in tokens if token in lowered)
        if score:
            scored.append((score, clean[:320]))
    scored.sort(key=lambda row: (row[0], len(row[1])), reverse=True)
    return [sentence for _, sentence in scored[:limit]]


def _duplicate_key(event: EnrichedEvent) -> dict[str, str]:
    return {
        "main_entity": event.entities[0] if event.entities else "",
        "event_type": event.normalized_event_type,
        "title_key": " ".join(sorted(_tokens(event.title))[:8]),
    }


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,}", text) if len(token) >= 4}


def _normalize_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _dedupe(rows: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for row in rows:
        key = row.lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().split("@")[ -1].split(":")[0]
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _canonical_url_key(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc.lower()}{parsed.path}".rstrip("/")


def _is_official_domain(domain: str) -> bool:
    return domain in OFFICIAL_DOMAINS or any(domain.endswith("." + item) for item in OFFICIAL_DOMAINS)
