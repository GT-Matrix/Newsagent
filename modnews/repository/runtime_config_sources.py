from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.repository.runtime_config_defaults import merge_builtin_newsnow, merge_builtin_rss

from .runtime_config_io import read_json


def rss_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or "").strip(),
        "name": str(row.get("name") or row.get("id") or "").strip(),
        "url": str(row.get("url") or "").strip(),
        "enabled": bool(row.get("enabled", True)),
        "content_type": str(row.get("content_type") or "news"),
    }


def update_rss(data: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    data["sources"]["rss"] = [rss_row(row) for row in items]
    return data


def update_rss_item(data: dict[str, Any], source_id: str, row: dict[str, Any]) -> dict[str, Any]:
    rows = [rss_row(item) for item in data["sources"].get("rss", []) if isinstance(item, dict)]
    next_row = rss_row({**row, "id": source_id})
    rows = [item for item in rows if item["id"] != source_id]
    rows.append(next_row)
    data["sources"]["rss"] = sorted(rows, key=lambda item: item["id"])
    return data


def delete_rss_item(data: dict[str, Any], source_id: str) -> dict[str, Any]:
    data["sources"]["rss"] = [
        row for row in data["sources"].get("rss", []) if isinstance(row, dict) and row.get("id") != source_id
    ]
    return data


def update_newsnow_item(data: dict[str, Any], source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    sources = data["sources"].setdefault("newsnow", {})
    row = sources.setdefault(source_id, {})
    if not isinstance(row, dict):
        row = {}
        sources[source_id] = row
    for key in ("enabled", "content_type"):
        if key in patch:
            row[key] = patch[key]
    return data


def update_site_list_item(data: dict[str, Any], source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    sources = data["sources"].setdefault("site_lists", {})
    exists = source_id in sources
    row = sources.setdefault(source_id, {"id": source_id})
    if not isinstance(row, dict):
        row = {"id": source_id}
        sources[source_id] = row
    for key in ("enabled", "name", "url", "content_type", "extractor_id", "tags", "options", "repair_policy"):
        if key in patch:
            row[key] = patch[key]
    if not exists:
        step = data["steps"].setdefault("site_lists", {})
        if isinstance(step, dict):
            sites = step.setdefault("sites", [])
            if isinstance(sites, list) and source_id not in sites:
                sites.append(source_id)
    return data


def delete_site_list_item(data: dict[str, Any], source_id: str) -> dict[str, Any]:
    sources = data["sources"].setdefault("site_lists", {})
    if isinstance(sources, dict):
        sources.pop(source_id, None)
    step = data["steps"].setdefault("site_lists", {})
    if isinstance(step, dict) and isinstance(step.get("sites"), list):
        step["sites"] = [item for item in step["sites"] if item != source_id]
    return data


def restore_builtin_sources(
    data: dict[str, Any],
    *,
    rss_seed_path: Path,
    newsnow_seed_path: Path,
) -> dict[str, Any]:
    merge_builtin_rss(data["sources"], read_json(rss_seed_path, default=[]), rss_row)
    merge_builtin_newsnow(data["sources"], read_json(newsnow_seed_path, default={}))
    return data


def enabled_rss_sources(data: dict[str, Any]) -> list[dict[str, Any]]:
    if not data["steps"]["rss"].get("enabled", True):
        return []
    return [row for row in data["sources"].get("rss", []) if isinstance(row, dict) and row.get("enabled", True)]


def enabled_newsnow_sources(data: dict[str, Any]) -> list[dict[str, Any]]:
    step = data["steps"]["newsnow"]
    if not step.get("enabled", True):
        return []
    allowed = set(step.get("columns", ["tech", "finance"]))
    include_all = bool(step.get("include_all", False))
    rows: list[dict[str, Any]] = []
    for source_id, row in data["sources"].get("newsnow", {}).items():
        if not isinstance(row, dict):
            continue
        if not row.get("enabled", True) or row.get("redirect"):
            continue
        if not include_all and row.get("column") not in allowed:
            continue
        rows.append({"id": source_id, **row})
    return sorted(rows, key=lambda item: item["id"])
