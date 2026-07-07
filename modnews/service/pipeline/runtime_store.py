from __future__ import annotations

from pathlib import Path
from typing import Any


_RUNTIME_RUN_STATE: dict[tuple[str, str], dict[str, Any]] = {}


def runtime_run_state(project_root: Path, run_id: str) -> dict[str, Any]:
    return dict(_RUNTIME_RUN_STATE.get(_runtime_key(project_root, run_id), {}))


def overlay_run_record(project_root: Path, run_record: dict[str, Any]) -> dict[str, Any]:
    run_id = str(run_record.get("run_id") or "")
    if not run_id:
        return dict(run_record)
    overlay = runtime_run_state(project_root, run_id)
    if not overlay:
        return dict(run_record)
    merged = dict(run_record)
    merged.update(overlay)
    return merged


def callback_events_for_run(project_root: Path, run_id: str) -> list[dict[str, Any]]:
    overlay = runtime_run_state(project_root, run_id)
    events = overlay.get("step_callback_events")
    return [item for item in events if isinstance(item, dict)] if isinstance(events, list) else []


def update_runtime_run_state(
    project_root: Path,
    run_id: str,
    patch: dict[str, Any],
    *,
    base_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = _runtime_key(project_root, run_id)
    current = dict(_RUNTIME_RUN_STATE.get(key, {}))
    current.update(patch)
    _RUNTIME_RUN_STATE[key] = current
    merged = dict(base_record or {})
    merged.update(current)
    return merged


def _runtime_key(project_root: Path, run_id: str) -> tuple[str, str]:
    return (str(project_root.resolve()), run_id)
