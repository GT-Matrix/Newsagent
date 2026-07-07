from __future__ import annotations

from typing import Any

from .runtime_config_defaults import default_classification, default_site_lists, default_steps


def needs_migration(data: dict[str, Any]) -> bool:
    return data.get("version") != 2 or "classification" not in data or "sources" not in data


def migrate_runtime_config(data: dict[str, Any], *, now: str, rss_row) -> dict[str, Any]:
    base = {
        "version": 2,
        "meta": {
            "created_at": data.get("meta", {}).get("created_at") if isinstance(data.get("meta"), dict) else now,
            "updated_at": now,
            "description": "Unified runtime configuration. Paths and secrets stay in environment variables.",
        },
        "steps": default_steps(),
        "classification": default_classification(),
        "sources": {"rss": [], "newsnow": {}, "site_lists": default_site_lists()},
    }
    if isinstance(data.get("steps"), dict):
        for key, value in data["steps"].items():
            if isinstance(value, dict):
                base["steps"].setdefault(key, {}).update(value)
    if isinstance(data.get("classification"), dict):
        base["classification"].update(strip_path_keys(data["classification"]))
    sources = data.get("sources")
    if isinstance(sources, dict):
        if isinstance(sources.get("rss"), list):
            base["sources"]["rss"] = [rss_row(row) for row in sources["rss"] if isinstance(row, dict)]
        if isinstance(sources.get("newsnow"), dict):
            base["sources"]["newsnow"] = sources["newsnow"]
        if isinstance(sources.get("site_lists"), dict):
            base["sources"]["site_lists"].update(sources["site_lists"])
    if isinstance(data.get("rss"), list):
        base["sources"]["rss"] = [rss_row(row) for row in data["rss"] if isinstance(row, dict)]
    old_newsnow = data.get("newsnow")
    if isinstance(old_newsnow, dict):
        if isinstance(old_newsnow.get("sources"), dict):
            base["sources"]["newsnow"] = old_newsnow["sources"]
        if isinstance(old_newsnow.get("columns"), list):
            base["steps"]["newsnow"]["columns"] = [str(item) for item in old_newsnow["columns"]]
        base["steps"]["newsnow"]["include_all"] = bool(old_newsnow.get("include_all", False))
    return base


def strip_path_keys(data: dict[str, Any]) -> dict[str, Any]:
    stripped = dict(data)
    for key in ("output_path", "events_output_path", "discarded_output_path", "checkpoint_path", "decisions_output_path"):
        stripped.pop(key, None)
    for nested in ("llm", "embedding"):
        if isinstance(stripped.get(nested), dict):
            stripped[nested] = dict(stripped[nested])
            stripped[nested].pop("cache_path", None)
    return stripped
