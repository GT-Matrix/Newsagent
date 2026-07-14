from __future__ import annotations


OFFICIAL_PLATFORMS = {
    "openai",
    "anthropic",
    "google-deepmind",
    "nvidia",
    "microsoft",
    "aws-ml",
    "meta-ai",
    "mistral",
    "huggingface",
    "huggingface_papers_trending",
    "stanford_hai",
    "arxiv",
}

AUTHORITY_MEDIA = {
    "techcrunch-ai",
    "the-verge-ai",
    "mit-technology-review",
    "mit-tech-review",
    "venturebeat",
    "ars-technica",
    "reuters",
    "wired",
    "wired-ai",
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
    "linux_do",
    "aihot",
    "v2ex-share",
    "juejin",
    "coolapk",
    "hacker-news",
    "hackernews",
    "product-hunt",
    "producthunt",
    "reddit",
    "github-trending",
    "github-trending-today",
}


def platform_score(platform: str) -> float:
    normalized = platform.strip().lower()
    if normalized in OFFICIAL_PLATFORMS | AUTHORITY_MEDIA | CHINESE_MEDIA | COMMUNITY_PLATFORMS:
        return 78.0
    return 72.0


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
