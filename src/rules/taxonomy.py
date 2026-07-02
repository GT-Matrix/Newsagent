from __future__ import annotations


EVENT_TYPE_ALIASES = {
    "product_launch": "product_release",
    "product launch": "product_release",
    "feature_launch": "product_release",
    "产品发布": "product_release",
    "产品更新": "product_release",
    "产品升级": "product_release",
    "新产品": "product_release",
    "AI产品发布": "product_release",
    "AI产品内测": "product_release",
    "模型发布": "model_release",
    "model_release": "model_release",
    "AI模型发布": "model_release",
    "AI模型更新": "model_release",
    "partnership": "partnership",
    "合作": "partnership",
    "政策合作": "partnership",
    "funding": "funding",
    "融资": "funding",
    "投资": "funding",
    "收购": "acquisition",
    "research": "research",
    "paper": "research",
    "arxiv": "research",
    "AI研究": "research",
    "技术突破": "research",
    "科研资助": "research",
    "benchmark": "benchmark",
    "政策发布": "policy",
    "政策限制": "policy",
    "公司政策": "company_policy",
    "公司业绩": "company_business",
    "公司重组": "company_business",
    "机构重组": "company_business",
    "AI硬件": "hardware",
    "AI芯片技术": "hardware",
    "芯片策略": "hardware",
    "AI基础设施": "infrastructure",
    "open_source_announcement": "open_source",
    "工具发布": "tooling",
    "product discovery": "rumor",
    "诉讼": "legal",
}

NEWS_TYPES = {
    "product_release",
    "model_release",
    "partnership",
    "funding",
    "acquisition",
    "policy",
    "company_policy",
    "company_business",
    "hardware",
    "infrastructure",
    "legal",
}

INSIGHT_TYPES = {
    "research",
    "benchmark",
}

DEEP_ASSET_TYPES = {
    "open_source",
    "tooling",
}

HIGH_IMPACT_TYPES = {
    "model_release",
    "policy",
    "hardware",
    "infrastructure",
    "partnership",
    "legal",
}

RUMOR_WORDS = {
    "rumor",
    "reportedly",
    "消息称",
    "据称",
    "预计",
    "或将",
    "疑似",
    "seems",
    "appears",
}

AI_KEYWORDS = {
    "ai",
    "llm",
    "agent",
    "agents",
    "chatgpt",
    "codex",
    "claude",
    "gemini",
    "gpt",
    "openai",
    "anthropic",
    "deepmind",
    "nvidia",
    "copilot",
    "model",
    "inference",
    "芯片",
    "模型",
    "智能体",
    "大模型",
    "人工智能",
    "推理",
    "算力",
}


def normalize_event_type(raw_type: str) -> str:
    raw = (raw_type or "").strip()
    return EVENT_TYPE_ALIASES.get(raw, EVENT_TYPE_ALIASES.get(raw.lower(), raw.lower() or "unknown"))
