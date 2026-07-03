from __future__ import annotations


OFFICIAL_PLATFORMS = {
    "openai",
    "anthropic",
    "google-deepmind",
    "nvidia",
    "microsoft",
    "aws-ml",
    "meta-ai",
    "huggingface",
    "huggingface_papers_trending",
    "stanford_hai",
    "arxiv",
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
    "36kr_ai",
    "wallstreetcn-news",
    "cls-depth",
    "solidot",
    "infoq",
    "jiqizhixin",
    "zhidx",
    "qbitai",
}

COMMUNITY_PLATFORMS = {
    "aihot",
    "hacker-news",
    "product-hunt",
    "reddit",
    "github-trending",
}


def platform_score(platform: str) -> float:
    normalized = platform.strip().lower()
    if normalized in OFFICIAL_PLATFORMS:
        return 94.0
    if normalized in AUTHORITY_MEDIA:
        return 86.0
    if normalized in CHINESE_MEDIA:
        return 78.0
    if normalized in COMMUNITY_PLATFORMS:
        return 64.0
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
