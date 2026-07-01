from __future__ import annotations

from src.models import ContentLayer, EventCandidate
from src.rules.taxonomy import INSIGHT_TYPES, NEWS_TYPES, normalize_event_type
from src.utils.text import has_any_word


DEEP_ASSET_TYPES_STRICT = {
    "open_source",
    "tooling",
    "framework",
    "library",
    "course",
    "book",
    "paper",
}

DEEP_ASSET_WORDS = {
    "github",
    "open source",
    "opensource",
    "repo",
    "repository",
    "framework",
    "library",
    "toolkit",
    "sdk",
    "course",
    "book",
    "readme",
    "benchmark suite",
    "dataset",
    "\u5f00\u6e90",
    "\u4ed3\u5e93",
    "\u6846\u67b6",
    "\u5de5\u5177",
    "\u8bfe\u7a0b",
    "\u4e66",
    "\u6570\u636e\u96c6",
}

INSIGHT_WORDS = {
    "paper",
    "research",
    "benchmark",
    "study",
    "method",
    "evaluation",
    "experiment",
    "\u8bba\u6587",
    "\u7814\u7a76",
    "\u8bc4\u6d4b",
    "\u65b9\u6cd5",
}

NEWS_OVERRIDE_TYPES = {
    "model_release",
    "product_release",
    "policy",
    "partnership",
    "funding",
    "acquisition",
    "hardware",
    "infrastructure",
    "legal",
    "company_business",
    "company_policy",
}


def classify_event(candidate: EventCandidate) -> tuple[ContentLayer, str]:
    normalized_type = normalize_event_type(candidate.event_type)
    haystack = " ".join(
        [
            candidate.event_label,
            candidate.event_summary,
            " ".join(candidate.representative_titles),
            " ".join(candidate.key_entities),
            normalized_type,
        ]
    )

    if normalized_type == "rumor":
        return "noise", normalized_type
    if normalized_type in NEWS_OVERRIDE_TYPES or normalized_type in NEWS_TYPES:
        return "news", normalized_type
    if normalized_type in INSIGHT_TYPES or has_any_word(haystack, INSIGHT_WORDS):
        return "insight", normalized_type
    if normalized_type in DEEP_ASSET_TYPES_STRICT or has_any_word(haystack, DEEP_ASSET_WORDS):
        return "deep_asset", normalized_type
    return "news", normalized_type