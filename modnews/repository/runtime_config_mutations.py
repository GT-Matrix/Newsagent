from __future__ import annotations

from typing import Any

from modnews.repository.runtime_config_defaults import editable_step_keys


def apply_step_patch(data: dict[str, Any], step_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    step = data["steps"].setdefault(step_id, {})
    if not isinstance(step, dict):
        step = {}
        data["steps"][step_id] = step
    for key, value in patch.items():
        if key in editable_step_keys(step_id):
            step[key] = value
    return data


def apply_classification_patch(data: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
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
    return data
