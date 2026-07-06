from __future__ import annotations

from pathlib import Path
from typing import Any


def default_steps() -> dict[str, Any]:
    return {
        "rss": {"enabled": True, "limit_per_feed": 20},
        "newsnow": {
            "enabled": True,
            "include_all": False,
            "columns": ["tech", "finance"],
            "limit_per_source": 50,
            "retries": 2,
            "retry_delay": 1.0,
        },
        "site_lists": {
            "enabled": True,
            "sites": [],
            "limit_per_site": 10,
        },
    }


def default_classification() -> dict[str, Any]:
    return {
        "enabled": True,
        "batch_size": 40,
        "batch_concurrency": 20,
        "event_candidate_count": 5,
        "merge_candidate_count": 5,
        "time_window_hours": 72,
        "suspect_mode": "discard",
    }


def default_site_lists() -> dict[str, Any]:
    return {}


def editable_step_keys(step_id: str) -> set[str]:
    return {
        "rss": {"enabled", "limit_per_feed"},
        "newsnow": {"enabled", "include_all", "columns", "limit_per_source", "retries", "retry_delay"},
        "site_lists": {"enabled", "sites", "limit_per_site"},
    }.get(step_id, {"enabled"})


def merge_builtin_rss(sources: dict[str, Any], seed_rows: list[dict[str, Any]], rss_row) -> None:
    existing = {
        row.get("id"): rss_row(row)
        for row in sources.get("rss", [])
        if isinstance(row, dict) and row.get("id")
    }
    for row in seed_rows:
        if not isinstance(row, dict):
            continue
        seed = rss_row(row)
        if not seed["id"]:
            continue
        current = existing.get(seed["id"])
        if current:
            seed["enabled"] = current.get("enabled", seed["enabled"])
            seed["content_type"] = current.get("content_type", seed["content_type"])
            seed["name"] = current.get("name") or seed["name"]
            seed["url"] = current.get("url") or seed["url"]
        existing[seed["id"]] = seed
    sources["rss"] = sorted(existing.values(), key=lambda item: item["id"])


def merge_builtin_newsnow(sources: dict[str, Any], seed_data: dict[str, Any]) -> None:
    newsnow = sources.setdefault("newsnow", {})
    if not isinstance(newsnow, dict):
        newsnow = {}
        sources["newsnow"] = newsnow
    for source_id, meta in seed_data.items():
        if not isinstance(meta, dict):
            continue
        current = newsnow.get(source_id)
        if not isinstance(current, dict):
            current = {}
        newsnow[source_id] = {
            "enabled": current.get("enabled", not bool(meta.get("disabled") or meta.get("redirect"))),
            "name": current.get("name") or meta.get("name") or source_id,
            "title": current.get("title", meta.get("title")),
            "column": current.get("column") or meta.get("column", ""),
            "type": current.get("type") or meta.get("type", ""),
            "home": current.get("home") or meta.get("home", ""),
            "color": current.get("color") or meta.get("color", ""),
            "redirect": current.get("redirect", meta.get("redirect")),
            "content_type": current.get("content_type", "news"),
        }


def build_initial_config(
    *,
    now: str,
    rss_rows: list[dict[str, Any]],
    newsnow_data: dict[str, Any],
) -> dict[str, Any]:
    newsnow_sources = {}
    for source_id, meta in newsnow_data.items():
        if isinstance(meta, dict):
            newsnow_sources[source_id] = {
                "enabled": not bool(meta.get("disabled") or meta.get("redirect")),
                "name": meta.get("name") or source_id,
                "title": meta.get("title"),
                "column": meta.get("column", ""),
                "type": meta.get("type", ""),
                "home": meta.get("home", ""),
                "color": meta.get("color", ""),
                "redirect": meta.get("redirect"),
                "content_type": "news",
            }
    return {
        "version": 2,
        "meta": {
            "created_at": now,
            "updated_at": now,
            "description": "Unified runtime configuration. Paths and secrets stay in environment variables.",
        },
        "steps": default_steps(),
        "classification": default_classification(),
        "sources": {
            "rss": rss_rows,
            "newsnow": newsnow_sources,
            "site_lists": default_site_lists(),
        },
    }
