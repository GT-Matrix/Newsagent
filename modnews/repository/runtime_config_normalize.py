from __future__ import annotations

from typing import Any

from .runtime_config_defaults import default_classification, default_site_lists, default_steps


def normalize_config(data: dict[str, Any], *, now: str, rss_row) -> dict[str, Any]:
    config = {
        key: data[key]
        for key in ("version", "meta", "steps", "classification", "sources")
        if key in data
    }
    config["version"] = 2
    meta = config.setdefault("meta", {})
    if not isinstance(meta, dict):
        meta = {}
        config["meta"] = meta
    meta.setdefault("created_at", now)
    meta.setdefault("description", "Unified runtime configuration. Paths and secrets stay in environment variables.")

    steps = config.setdefault("steps", {})
    if not isinstance(steps, dict):
        steps = {}
        config["steps"] = steps
    steps = {key: value for key, value in steps.items() if key in default_steps()}
    config["steps"] = steps
    for key, value in default_steps().items():
        row = steps.setdefault(key, {})
        if isinstance(row, dict):
            for item_key, item_value in value.items():
                row.setdefault(item_key, item_value)

    classification = config.setdefault("classification", {})
    if not isinstance(classification, dict):
        classification = {}
        config["classification"] = classification
    classification.pop("llm", None)
    classification.pop("embedding", None)
    deep_defaults(classification, default_classification())

    sources = config.setdefault("sources", {})
    if not isinstance(sources, dict):
        sources = {}
        config["sources"] = sources
    sources["rss"] = [rss_row(row) for row in sources.get("rss", []) if isinstance(row, dict)]

    newsnow = sources.setdefault("newsnow", {})
    if isinstance(newsnow, dict):
        for row in newsnow.values():
            if isinstance(row, dict):
                row.setdefault("content_type", "news")
    else:
        sources["newsnow"] = {}

    site_lists = sources.setdefault("site_lists", {})
    if not isinstance(site_lists, dict):
        site_lists = {}
        sources["site_lists"] = site_lists
    for source_id, default in default_site_lists().items():
        row = site_lists.setdefault(source_id, {})
        if isinstance(row, dict):
            for key, value in default.items():
                row.setdefault(key, value)
    for source_id, row in site_lists.items():
        if not isinstance(row, dict):
            continue
        row.setdefault("content_type", "news")
        row.setdefault("extractor_id", source_id)
        row.setdefault("tags", [])
        row.setdefault("repair_policy", {"enabled": True, "max_attempts_before_repair": 3, "auto_start": True})
    return config


def deep_defaults(target: dict[str, Any], defaults: dict[str, Any]) -> None:
    for key, value in defaults.items():
        if isinstance(value, dict):
            row = target.setdefault(key, {})
            if isinstance(row, dict):
                deep_defaults(row, value)
            else:
                target[key] = dict(value)
        else:
            target.setdefault(key, value)
