from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.core.paths import runtime_paths


@dataclass(slots=True)
class RuntimeConfigStore:
    project_root: Path

    @property
    def path(self) -> Path:
        return runtime_paths(self.project_root).config_path

    @property
    def legacy_source_config_path(self) -> Path:
        return runtime_paths(self.project_root).legacy_source_config_path

    @property
    def rss_seed_path(self) -> Path:
        return self.project_root / "modnews_pipeline" / "data" / "rss_sources.json"

    @property
    def newsnow_seed_path(self) -> Path:
        return self.project_root / "modnews_pipeline" / "data" / "newsnow_sources.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            self.save(self._initial_config())
            return _read_json(self.path)
        original = _read_json(self.path)
        data = original
        if _needs_migration(data):
            data = self._migrate(data)
        data = _normalize_config(data)
        if data != original:
            self.save(data)
        return data

    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        data = _normalize_config(data)
        data.setdefault("meta", {})["updated_at"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            current = self.path.read_text(encoding="utf-8")
            next_text = json.dumps(data, ensure_ascii=False, indent=2)
            if current != next_text:
                _backup_config(self.path)
                self.path.write_text(next_text, encoding="utf-8")
                return data
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def update_step(self, step_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        step = data["steps"].setdefault(step_id, {})
        if not isinstance(step, dict):
            step = {}
            data["steps"][step_id] = step
        for key, value in patch.items():
            if key in _editable_step_keys(step_id):
                step[key] = value
        return self.save(data)

    def update_classification(self, patch: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        target = data.setdefault("classification", {})
        for key in (
            "enabled",
            "batch_size",
            "batch_concurrency",
            "event_candidate_count",
            "merge_candidate_count",
            "time_window_hours",
            "suspect_mode",
        ):
            if key in patch:
                target[key] = patch[key]
        return self.save(data)

    def update_rss(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        data = self.load()
        data["sources"]["rss"] = [_rss_row(row) for row in items]
        return self.save(data)

    def update_rss_item(self, source_id: str, row: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        rows = [_rss_row(item) for item in data["sources"].get("rss", []) if isinstance(item, dict)]
        next_row = _rss_row({**row, "id": source_id})
        rows = [item for item in rows if item["id"] != source_id]
        rows.append(next_row)
        data["sources"]["rss"] = sorted(rows, key=lambda item: item["id"])
        return self.save(data)

    def delete_rss_item(self, source_id: str) -> dict[str, Any]:
        data = self.load()
        data["sources"]["rss"] = [
            row for row in data["sources"].get("rss", []) if isinstance(row, dict) and row.get("id") != source_id
        ]
        return self.save(data)

    def update_newsnow_item(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        sources = data["sources"].setdefault("newsnow", {})
        row = sources.setdefault(source_id, {})
        if not isinstance(row, dict):
            row = {}
            sources[source_id] = row
        for key in ("enabled", "content_type"):
            if key in patch:
                row[key] = patch[key]
        return self.save(data)

    def update_site_list_item(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
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
        return self.save(data)

    def restore_builtin_sources(self) -> dict[str, Any]:
        data = self.load()
        _merge_builtin_rss(data["sources"], self.rss_seed_path)
        _merge_builtin_newsnow(data["sources"], self.newsnow_seed_path)
        return self.save(data)

    def enabled_rss_sources(self) -> list[dict[str, Any]]:
        data = self.load()
        if not data["steps"]["rss"].get("enabled", True):
            return []
        return [row for row in data["sources"].get("rss", []) if isinstance(row, dict) and row.get("enabled", True)]

    def enabled_newsnow_sources(self) -> list[dict[str, Any]]:
        data = self.load()
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

    def _initial_config(self) -> dict[str, Any]:
        if self.legacy_source_config_path.exists():
            legacy = _read_json(self.legacy_source_config_path)
            if isinstance(legacy, dict):
                return self._migrate(legacy)
        rss_rows = [_rss_row(row) for row in _read_json(self.rss_seed_path, default=[])]
        newsnow_data = _read_json(self.newsnow_seed_path)
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
                "created_at": _now(),
                "updated_at": _now(),
                "description": "Unified runtime configuration. Paths and secrets stay in environment variables.",
            },
            "steps": _default_steps(),
            "classification": _default_classification(),
            "sources": {
                "rss": rss_rows,
                "newsnow": newsnow_sources,
                "site_lists": _default_site_lists(),
            },
        }

    def _migrate(self, data: dict[str, Any]) -> dict[str, Any]:
        base = {
            "version": 2,
            "meta": {
                "created_at": data.get("meta", {}).get("created_at") if isinstance(data.get("meta"), dict) else _now(),
                "updated_at": _now(),
                "description": "Unified runtime configuration. Paths and secrets stay in environment variables.",
            },
            "steps": _default_steps(),
            "classification": _default_classification(),
            "sources": {"rss": [], "newsnow": {}, "site_lists": _default_site_lists()},
        }
        if isinstance(data.get("steps"), dict):
            for key, value in data["steps"].items():
                if isinstance(value, dict):
                    base["steps"].setdefault(key, {}).update(value)
        if isinstance(data.get("classification"), dict):
            base["classification"].update(_strip_path_keys(data["classification"]))
        sources = data.get("sources")
        if isinstance(sources, dict):
            if isinstance(sources.get("rss"), list):
                base["sources"]["rss"] = [_rss_row(row) for row in sources["rss"] if isinstance(row, dict)]
            if isinstance(sources.get("newsnow"), dict):
                base["sources"]["newsnow"] = sources["newsnow"]
            if isinstance(sources.get("site_lists"), dict):
                base["sources"]["site_lists"].update(sources["site_lists"])
        if isinstance(data.get("rss"), list):
            base["sources"]["rss"] = [_rss_row(row) for row in data["rss"] if isinstance(row, dict)]
        old_newsnow = data.get("newsnow")
        if isinstance(old_newsnow, dict):
            if isinstance(old_newsnow.get("sources"), dict):
                base["sources"]["newsnow"] = old_newsnow["sources"]
            if isinstance(old_newsnow.get("columns"), list):
                base["steps"]["newsnow"]["columns"] = [str(item) for item in old_newsnow["columns"]]
            base["steps"]["newsnow"]["include_all"] = bool(old_newsnow.get("include_all", False))
        return base


def runtime_config_store(project_root: Path) -> RuntimeConfigStore:
    return RuntimeConfigStore(project_root)


class RuntimeConfigRepository:
    def __init__(self, project_root: Path) -> None:
        self.store = runtime_config_store(project_root)

    def load(self) -> dict[str, Any]:
        return self.store.load()

    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.store.save(data)

    def update_step(self, step_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_step(step_id, patch)

    def update_classification(self, patch: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_classification(patch)


def _default_steps() -> dict[str, Any]:
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


def _default_classification() -> dict[str, Any]:
    return {
        "enabled": True,
        "batch_size": 40,
        "batch_concurrency": 20,
        "event_candidate_count": 5,
        "merge_candidate_count": 5,
        "time_window_hours": 72,
        "suspect_mode": "discard",
    }


def _default_site_lists() -> dict[str, Any]:
    return {}


def _normalize_config(data: dict[str, Any]) -> dict[str, Any]:
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
    meta.setdefault("created_at", _now())
    meta.setdefault("description", "Unified runtime configuration. Paths and secrets stay in environment variables.")
    steps = config.setdefault("steps", {})
    if not isinstance(steps, dict):
        steps = {}
        config["steps"] = steps
    steps = {key: value for key, value in steps.items() if key in _default_steps()}
    config["steps"] = steps
    for key, value in _default_steps().items():
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
    _deep_defaults(classification, _default_classification())
    sources = config.setdefault("sources", {})
    if not isinstance(sources, dict):
        sources = {}
        config["sources"] = sources
    sources["rss"] = [_rss_row(row) for row in sources.get("rss", []) if isinstance(row, dict)]
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
    for source_id, default in _default_site_lists().items():
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


def _merge_builtin_rss(sources: dict[str, Any], seed_path: Path) -> None:
    existing = {
        row.get("id"): _rss_row(row)
        for row in sources.get("rss", [])
        if isinstance(row, dict) and row.get("id")
    }
    for row in _read_json(seed_path, default=[]):
        if not isinstance(row, dict):
            continue
        seed = _rss_row(row)
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


def _merge_builtin_newsnow(sources: dict[str, Any], seed_path: Path) -> None:
    newsnow = sources.setdefault("newsnow", {})
    if not isinstance(newsnow, dict):
        newsnow = {}
        sources["newsnow"] = newsnow
    for source_id, meta in _read_json(seed_path, default={}).items():
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


def _rss_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or "").strip(),
        "name": str(row.get("name") or row.get("id") or "").strip(),
        "url": str(row.get("url") or "").strip(),
        "enabled": bool(row.get("enabled", True)),
        "content_type": str(row.get("content_type") or "news"),
    }


def _needs_migration(data: dict[str, Any]) -> bool:
    return data.get("version") != 2 or "classification" not in data or "sources" not in data


def _strip_path_keys(data: dict[str, Any]) -> dict[str, Any]:
    stripped = dict(data)
    for key in ("output_path", "events_output_path", "discarded_output_path", "checkpoint_path", "decisions_output_path"):
        stripped.pop(key, None)
    for nested in ("llm", "embedding"):
        if isinstance(stripped.get(nested), dict):
            stripped[nested] = dict(stripped[nested])
            stripped[nested].pop("cache_path", None)
    return stripped


def _editable_step_keys(step_id: str) -> set[str]:
    return {
        "rss": {"enabled", "limit_per_feed"},
        "newsnow": {"enabled", "include_all", "columns", "limit_per_source", "retries", "retry_delay"},
        "site_lists": {"enabled", "sites", "limit_per_site"},
    }.get(step_id, {"enabled"})


def _deep_defaults(target: dict[str, Any], defaults: dict[str, Any]) -> None:
    for key, value in defaults.items():
        if isinstance(value, dict):
            row = target.setdefault(key, {})
            if isinstance(row, dict):
                _deep_defaults(row, value)
            else:
                target[key] = dict(value)
        else:
            target.setdefault(key, value)


def _read_json(path: Path, default: Any | None = None) -> Any:
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _backup_config(path: Path) -> None:
    backup_dir = path.parent / "config.backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d%H%M%S%f")
    shutil.copy2(path, backup_dir / f"{path.stem}-{stamp}{path.suffix}")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
