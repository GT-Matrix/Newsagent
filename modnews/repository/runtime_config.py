from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.core.paths import runtime_paths
from modnews.repository.runtime_config_defaults import (
    build_initial_config,
    editable_step_keys,
    merge_builtin_newsnow,
    merge_builtin_rss,
)
from modnews.repository.runtime_config_migration import migrate_runtime_config, needs_migration
from modnews.repository.runtime_config_normalize import normalize_config


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
        return self.project_root / "modnews" / "data" / "rss_sources.json"

    @property
    def newsnow_seed_path(self) -> Path:
        return self.project_root / "modnews" / "data" / "newsnow_sources.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            self.save(self._initial_config())
            return _read_json(self.path)
        original = _read_json(self.path)
        data = original
        if needs_migration(data):
            data = self._migrate(data)
        data = normalize_config(data, now=_now(), rss_row=_rss_row)
        if data != original:
            self.save(data)
        return data

    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        data = normalize_config(data, now=_now(), rss_row=_rss_row)
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
            if key in editable_step_keys(step_id):
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

    def delete_site_list_item(self, source_id: str) -> dict[str, Any]:
        data = self.load()
        sources = data["sources"].setdefault("site_lists", {})
        if isinstance(sources, dict):
            sources.pop(source_id, None)
        step = data["steps"].setdefault("site_lists", {})
        if isinstance(step, dict) and isinstance(step.get("sites"), list):
            step["sites"] = [item for item in step["sites"] if item != source_id]
        return self.save(data)

    def restore_builtin_sources(self) -> dict[str, Any]:
        data = self.load()
        merge_builtin_rss(data["sources"], _read_json(self.rss_seed_path, default=[]), _rss_row)
        merge_builtin_newsnow(data["sources"], _read_json(self.newsnow_seed_path, default={}))
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
        return build_initial_config(
            now=_now(),
            rss_rows=[_rss_row(row) for row in _read_json(self.rss_seed_path, default=[])],
            newsnow_data=_read_json(self.newsnow_seed_path, default={}),
        )

    def _migrate(self, data: dict[str, Any]) -> dict[str, Any]:
        return migrate_runtime_config(data, now=_now(), rss_row=_rss_row)


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


def _rss_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or "").strip(),
        "name": str(row.get("name") or row.get("id") or "").strip(),
        "url": str(row.get("url") or "").strip(),
        "enabled": bool(row.get("enabled", True)),
        "content_type": str(row.get("content_type") or "news"),
    }


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
