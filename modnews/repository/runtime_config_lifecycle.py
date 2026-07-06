from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from modnews.repository.runtime_config_defaults import build_initial_config
from modnews.repository.runtime_config_migration import migrate_runtime_config, needs_migration
from modnews.repository.runtime_config_normalize import normalize_config


def load_runtime_config(
    *,
    path: Path,
    legacy_source_config_path: Path,
    rss_seed_path: Path,
    newsnow_seed_path: Path,
    current_time: Callable[[], str],
    read_json: Callable[[Path, Any | None], Any],
    write_config: Callable[[Path, dict[str, Any]], None],
    rss_row,
) -> dict[str, Any]:
    if not path.exists():
        initial = build_initial_runtime_config(
            legacy_source_config_path=legacy_source_config_path,
            rss_seed_path=rss_seed_path,
            newsnow_seed_path=newsnow_seed_path,
            current_time=current_time,
            read_json=read_json,
            rss_row=rss_row,
        )
        save_runtime_config(
            path=path,
            data=initial,
            current_time=current_time,
            write_config=write_config,
            rss_row=rss_row,
        )
        return read_json(path)

    original = read_json(path)
    data = original
    if needs_migration(data):
        data = migrate_runtime_config(data, now=current_time(), rss_row=rss_row)
    data = normalize_config(data, now=current_time(), rss_row=rss_row)
    if data != original:
        save_runtime_config(
            path=path,
            data=data,
            current_time=current_time,
            write_config=write_config,
            rss_row=rss_row,
        )
    return data


def save_runtime_config(
    *,
    path: Path,
    data: dict[str, Any],
    current_time: Callable[[], str],
    write_config: Callable[[Path, dict[str, Any]], None],
    rss_row,
) -> dict[str, Any]:
    normalized = normalize_config(data, now=current_time(), rss_row=rss_row)
    normalized.setdefault("meta", {})["updated_at"] = current_time()
    write_config(path, normalized)
    return normalized


def build_initial_runtime_config(
    *,
    legacy_source_config_path: Path,
    rss_seed_path: Path,
    newsnow_seed_path: Path,
    current_time: Callable[[], str],
    read_json: Callable[[Path, Any | None], Any],
    rss_row,
) -> dict[str, Any]:
    if legacy_source_config_path.exists():
        legacy = read_json(legacy_source_config_path)
        if isinstance(legacy, dict):
            return migrate_runtime_config(legacy, now=current_time(), rss_row=rss_row)
    return build_initial_config(
        now=current_time(),
        rss_rows=[rss_row(row) for row in read_json(rss_seed_path, default=[])],
        newsnow_data=read_json(newsnow_seed_path, default={}),
    )
