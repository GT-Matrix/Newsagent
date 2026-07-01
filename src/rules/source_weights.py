from __future__ import annotations


OFFICIAL_PLATFORMS = {
    "openai",
    "anthropic",
    "google-deepmind",
    "nvidia",
    "microsoft",
    "meta-ai",
    "huggingface",
    "stanford_hai",
}

AUTHORITY_MEDIA = {
    "techcrunch-ai",
    "the-verge-ai",
    "mit-technology-review",
    "venturebeat",
    "ars-technica",
    "reuters",
    "wired",
}

CHINESE_MEDIA = {
    "aibase",
    "wallstreetcn-news",
    "cls-depth",
    "solidot",
    "infoq",
    "jiqizhixin",
    "qbitai",
}

COMMUNITY_PLATFORMS = {
    "linux_do",
    "aihot",
    "hacker-news",
    "product-hunt",
    "reddit",
    "github-trending",
}


def platform_score(platform: str) -> float:
    normalized = platform.strip().lower()
    if normalized in OFFICIAL_PLATFORMS:
        return 96.0
    if normalized in AUTHORITY_MEDIA:
        return 84.0
    if normalized in CHINESE_MEDIA:
        return 70.0
    if normalized in COMMUNITY_PLATFORMS:
        return 48.0
    return 62.0


def source_kind(platform: str) -> str:
    normalized = platform.strip().lower()
    if normalized in OFFICIAL_PLATFORMS:
        return "official"
    if normalized in AUTHORITY_MEDIA:
        return "authority_media"
    if normalized in CHINESE_MEDIA:
        return "chinese_media"
    if normalized in COMMUNITY_PLATFORMS:
        return "community"
    return "unknown"
