from __future__ import annotations

import re

from src.models import EventCandidate
from src.rules.scoring_rules import WHY_IMPORTANT_BY_TYPE
from src.utils.text import choose_best_title, mostly_english, short_sentence


TYPE_NOUNS = {
    "model_release": "\u6a21\u578b\u53d1\u5e03",
    "product_release": "\u4ea7\u54c1\u66f4\u65b0",
    "policy": "\u653f\u7b56\u4e0e\u5408\u89c4\u52a8\u6001",
    "partnership": "\u5408\u4f5c\u52a8\u6001",
    "hardware": "AI \u786c\u4ef6\u52a8\u6001",
    "infrastructure": "AI \u57fa\u7840\u8bbe\u65bd\u52a8\u6001",
    "research": "\u7814\u7a76\u8fdb\u5c55",
    "benchmark": "\u8bc4\u6d4b\u4e0e\u57fa\u51c6\u52a8\u6001",
    "open_source": "\u5f00\u6e90\u9879\u76ee",
    "tooling": "\u5de5\u5177\u66f4\u65b0",
    "funding": "\u878d\u8d44\u52a8\u6001",
    "legal": "\u6cd5\u5f8b\u4e0e\u7248\u6743\u52a8\u6001",
}

TITLE_REWRITES = [
    ("openai has new ai models", "OpenAI \u65b0\u6a21\u578b\u53d1\u5e03\u53d7\u9650"),
    ("nvidia-aws ai production collaboration", "NVIDIA \u4e0e AWS \u5408\u4f5c\u63a8\u52a8 AI \u751f\u4ea7\u7ea7\u90e8\u7f72"),
    ("diffusiongemma", "DiffusionGemma \u6587\u672c\u751f\u6210\u6a21\u578b\u53d1\u5e03"),
    ("gemma 4 12b", "Gemma 4 12B \u591a\u6a21\u6001\u6a21\u578b\u53d1\u5e03"),
    ("pp-ocrv6", "PP-OCRv6 \u591a\u8bed\u8a00 OCR \u6a21\u578b\u53d1\u5e03"),
    ("france advances", "\u6cd5\u56fd\u501f\u52a9 NVIDIA \u6280\u672f\u63a8\u8fdb\u6b27\u6d32 AI \u5e03\u5c40"),
    ("policy on the ai exponential", "Anthropic \u53d1\u5e03 AI \u6307\u6570\u589e\u957f\u653f\u7b56"),
    ("ffasr", "FFASR \u771f\u5b9e\u573a\u666f ASR \u8bc4\u6d4b\u699c\u5355\u53d1\u5e03"),
    ("lifescibench", "OpenAI \u53d1\u5e03\u751f\u547d\u79d1\u5b66 AI \u57fa\u51c6 LifeSciBench"),
    ("cuga", "CUGA \u667a\u80fd\u4f53\u5e94\u7528\u6846\u67b6\u53d1\u5e03"),
    ("openai academy", "OpenAI Academy \u63a8\u51fa\u9762\u5411\u672a\u6765\u5de5\u4f5c\u7684 AI \u8bfe\u7a0b"),
    ("ornith-1.0", "Ornith-1.0 \u667a\u80fd\u4f53\u7f16\u7a0b\u6a21\u578b\u53d1\u5e03"),
]

SUMMARY_REWRITES = [
    ("openai has new ai models", "OpenAI \u56e0\u653f\u5e9c\u5ba1\u6279\u8981\u6c42\u9650\u5236\u65b0\u6a21\u578b\u53d1\u5e03\u8303\u56f4\u3002"),
    ("nvidia-aws ai production collaboration", "NVIDIA \u4e0e AWS \u5408\u4f5c\uff0c\u63a8\u52a8 AI \u6a21\u578b\u8bad\u7ec3\u548c\u4f01\u4e1a\u751f\u4ea7\u90e8\u7f72\u3002"),
    ("diffusiongemma", "Google DeepMind \u53d1\u5e03 DiffusionGemma\uff0c\u4e3b\u6253\u66f4\u5feb\u7684\u6587\u672c\u751f\u6210\u3002"),
    ("gemma 4 12b", "Google DeepMind \u53d1\u5e03 Gemma 4 12B\uff0c\u5b9a\u4f4d\u4e3a\u7edf\u4e00\u7684\u591a\u6a21\u6001\u6a21\u578b\u3002"),
    ("pp-ocrv6", "Hugging Face \u4e0a\u7ebf PP-OCRv6 \u591a\u8bed\u8a00 OCR \u6a21\u578b\uff0c\u8986\u76d6\u591a\u79cd\u8bed\u8a00\u573a\u666f\u3002"),
    ("france advances", "\u6cd5\u56fd\u6b63\u501f\u52a9 NVIDIA \u6280\u672f\u63a8\u52a8\u6b27\u6d32 AI \u57fa\u7840\u8bbe\u65bd\u548c\u4ea7\u4e1a\u5e03\u5c40\u3002"),
    ("policy on the ai exponential", "Anthropic \u53d1\u5e03\u5173\u4e8e AI \u6307\u6570\u589e\u957f\u7684\u653f\u7b56\u7acb\u573a\u3002"),
    ("ffasr", "FFASR \u63a8\u51fa\u9762\u5411\u771f\u5b9e\u573a\u666f\u7684 ASR \u80fd\u529b\u8bc4\u6d4b\u699c\u5355\u3002"),
    ("lifescibench", "OpenAI \u53d1\u5e03 LifeSciBench\uff0c\u7528\u4e8e\u8bc4\u4f30 AI \u5728\u751f\u547d\u79d1\u5b66\u4efb\u52a1\u4e2d\u7684\u80fd\u529b\u3002"),
    ("cuga", "Hugging Face \u53d1\u5e03 CUGA\uff0c\u63d0\u4f9b\u591a\u4e2a\u667a\u80fd\u4f53\u5e94\u7528\u793a\u4f8b\u548c\u8f7b\u91cf\u5de5\u5177\u6846\u67b6\u3002"),
    ("openai academy", "OpenAI Academy \u63a8\u51fa\u65b0\u8bfe\u7a0b\uff0c\u805a\u7126 AI \u5728\u672a\u6765\u5de5\u4f5c\u4e2d\u7684\u5e94\u7528\u3002"),
    ("ornith-1.0", "Ornith-1.0 \u662f\u9762\u5411\u667a\u80fd\u4f53\u7f16\u7a0b\u7684\u5f00\u6e90\u6a21\u578b\u7ebf\u7d22\uff0c\u4ecd\u9700\u590d\u6838\u3002"),
]

ACTION_PATTERNS = [
    (re.compile(r"\bintroduc(?:e|es|ed|ing)\b", re.I), "\u63a8\u51fa"),
    (re.compile(r"\breleas(?:e|es|ed|ing)\b", re.I), "\u53d1\u5e03"),
    (re.compile(r"\blaunch(?:es|ed|ing)?\b", re.I), "\u4e0a\u7ebf"),
    (re.compile(r"\bpartner(?:s|ed|ing)?\b|\bcollaborat(?:e|es|ed|ing)\b", re.I), "\u5408\u4f5c\u63a8\u8fdb"),
    (re.compile(r"\blimit(?:s|ed|ing)?\b|\brestrict(?:s|ed|ing)?\b", re.I), "\u9650\u5236"),
]

FALLBACK_FACT_PATTERNS = [
    ("microsoft 365 copilot", "\u5df2\u6210\u4e3a Microsoft 365 Copilot \u7684\u9996\u9009\u6a21\u578b"),
    ("amazon bedrock", "\u5df2\u53ef\u901a\u8fc7 Amazon Bedrock \u4f7f\u7528"),
    ("agent arena", "\u5728 Agent Arena \u771f\u5b9e\u667a\u80fd\u4f53\u4f1a\u8bdd\u8bc4\u6d4b\u4e2d\u6392\u540d\u7b2c\u4e8c"),
    ("aa-briefcase", "\u53d1\u5e03 AA-Briefcase\uff0c\u7528\u4e8e\u8861\u91cf\u590d\u6742\u667a\u80fd\u4f53\u4efb\u52a1\u7684\u6210\u672c"),
    ("erdos", "\u6709\u7528\u6237\u79f0\u5176\u7ed9\u51fa\u4e86 Erd\u0151s \u6570\u5b66\u95ee\u9898\u7684\u89e3\u6cd5\uff0c\u4ecd\u5f85\u72ec\u7acb\u9a8c\u8bc1"),
    ("trade secret", "\u82f9\u679c\u6307\u63a7 OpenAI \u6d89\u53ca AI \u786c\u4ef6\u76f8\u5173\u5546\u4e1a\u673a\u5bc6"),
]


def summarize_event(candidate: EventCandidate, normalized_type: str) -> tuple[str, str, str]:
    raw_title = choose_best_title(candidate.event_label, candidate.representative_titles)
    title = _rewrite_title(raw_title)
    one_sentence = short_sentence(candidate.event_summary, title)
    one_sentence = _rewrite_summary(raw_title, one_sentence) or one_sentence
    if mostly_english(one_sentence) or _is_generic_summary(one_sentence, title):
        if not mostly_english(title):
            one_sentence = short_sentence(title, title)
        else:
            one_sentence = _chinese_sentence(candidate, title, one_sentence, normalized_type)
    one_sentence = _add_source_fact(candidate, one_sentence)
    why = _why_important(candidate, normalized_type)
    return title, one_sentence, why


def _rewrite_title(title: str) -> str:
    lowered = title.lower()
    for key, value in TITLE_REWRITES:
        if key in lowered:
            return value
    return title


def _rewrite_summary(title: str, summary: str) -> str | None:
    lowered = f"{title} {summary}".lower()
    for key, value in SUMMARY_REWRITES:
        if key in lowered:
            return value
    return None


def _chinese_sentence(candidate: EventCandidate, title: str, summary: str, normalized_type: str) -> str:
    subject = _subject(candidate, title)
    action = _action(summary, title)
    noun = TYPE_NOUNS.get(normalized_type, "AI \u52a8\u6001")
    detail = _detail(summary, title)
    if detail:
        return f"{subject}{action}{noun}\uff0c\u91cd\u70b9\u6d89\u53ca{detail}\u3002"
    return f"{subject}{action}{noun}\u3002"


def _is_generic_summary(summary: str, title: str) -> bool:
    compact = " ".join(summary.split()).rstrip("\u3002.!\uff01?")
    return not compact or compact == title.rstrip("\u3002.!\uff01?") or len(compact) < 14


def _add_source_fact(candidate: EventCandidate, summary: str) -> str:
    source_text = " ".join(source.title for source in candidate.source_items).lower()
    for marker, fact in FALLBACK_FACT_PATTERNS:
        if marker in source_text:
            clean = summary.rstrip("\u3002.!\uff01?")
            if marker in clean.lower():
                return summary
            if marker == "trade secret" and "\u5546\u4e1a\u673a\u5bc6" in clean:
                return summary
            return f"{clean}\uff0c{fact}\u3002"
    return summary


def _why_important(candidate: EventCandidate, normalized_type: str) -> str:
    source_text = " ".join(source.title for source in candidate.source_items).lower()
    if normalized_type == "model_release" and "microsoft 365 copilot" in source_text:
        return "\u6a21\u578b\u8fdb\u5165\u4e3b\u6d41\u529e\u516c\u4ea7\u54c1\uff0c\u4f1a\u76f4\u63a5\u5f71\u54cd\u4f01\u4e1a AI \u52a9\u624b\u7684\u80fd\u529b\u9009\u62e9\u3001\u6210\u672c\u548c\u7ade\u4e89\u683c\u5c40\u3002"
    if normalized_type == "benchmark" and ("agent arena" in source_text or "aa-briefcase" in source_text):
        return "\u8fd9\u4e3a\u8bc4\u4f30\u667a\u80fd\u4f53\u5728\u771f\u5b9e\u4efb\u52a1\u4e2d\u7684\u80fd\u529b\u548c\u6210\u672c\u63d0\u4f9b\u4e86\u53ef\u6bd4\u8f83\u7684\u5916\u90e8\u4fe1\u53f7\u3002"
    if normalized_type == "legal" and "trade secret" in source_text:
        return "\u6848\u4ef6\u53ef\u80fd\u5f71\u54cd AI \u786c\u4ef6\u7684\u4eba\u624d\u6d41\u52a8\u3001\u5546\u4e1a\u673a\u5bc6\u4fdd\u62a4\u4e0e\u5934\u90e8\u516c\u53f8\u7684\u5408\u4f5c\u8fb9\u754c\u3002"
    if normalized_type == "product":
        return "产品能力和可用范围的变化，会影响团队对同类 AI 工具的选型与接入节奏。"
    if normalized_type == "company":
        return "头部公司的关键人事变化，可能影响其产品路线、组织稳定性和合作预期。"
    if normalized_type == "security":
        return "这提示企业在引入 AI 功能时，需要把数据授权、隐私保护和用户告知前置处理。"
    return WHY_IMPORTANT_BY_TYPE.get(
        normalized_type,
        "\u8fd9\u6761\u4fe1\u606f\u4e0e AI \u884c\u4e1a\u52a8\u6001\u76f8\u5173\uff0c\u9002\u5408\u8fdb\u5165\u56e2\u961f\u60c5\u62a5\u6c60\u7ee7\u7eed\u89c2\u5bdf\u3002",
    )


def _subject(candidate: EventCandidate, title: str) -> str:
    for entity in candidate.key_entities:
        clean = entity.strip()
        if clean and not mostly_english(clean):
            return clean
    for entity in candidate.key_entities:
        clean = entity.strip()
        if clean:
            return clean
    match = re.match(r"([A-Z][A-Za-z0-9.&-]*(?:\s+[A-Z][A-Za-z0-9.&-]*){0,2})", title)
    if match:
        return match.group(1).strip()
    return "\u76f8\u5173\u673a\u6784"


def _action(*texts: str) -> str:
    text = " ".join(texts)
    for pattern, action in ACTION_PATTERNS:
        if pattern.search(text):
            return action
    return "\u66f4\u65b0"


def _detail(summary: str, title: str) -> str:
    text = f"{summary} {title}".lower()
    details: list[str] = []
    if "agent" in text:
        details.append("\u667a\u80fd\u4f53")
    if "coding" in text or "code" in text or "codex" in text:
        details.append("AI \u7f16\u7a0b")
    if "multimodal" in text:
        details.append("\u591a\u6a21\u6001\u80fd\u529b")
    if "benchmark" in text or "leaderboard" in text:
        details.append("\u80fd\u529b\u8bc4\u6d4b")
    if "inference" in text or "chip" in text or "hbm" in text:
        details.append("\u63a8\u7406\u4e0e\u7b97\u529b")
    if "policy" in text or "government" in text or "copyright" in text:
        details.append("\u653f\u7b56\u5408\u89c4")
    if "open-source" in text or "open source" in text:
        details.append("\u5f00\u6e90\u751f\u6001")
    return "\u3001".join(list(dict.fromkeys(details))[:3])
