from __future__ import annotations

from typing import Any

from modnews.core.config import apply_runtime_overrides, load_config


def load_runtime_plan(request: dict[str, Any]) -> tuple[str, str, object, Any]:
    run_id = str(request.get("run_id") or "local")
    project_root = str(request.get("project_root") or "")
    config_path = request.get("config")
    config = load_config(config_path, project_root=project_root)
    apply_runtime_overrides(
        config,
        only_ingest_steps=request.get("only_ingest_steps") or request.get("only"),
        disable_classification=bool(request.get("disable_classification")),
    )
    return run_id, project_root, config_path, config


def report_enabled(request: dict[str, Any]) -> bool:
    if bool(request.get("disable_report")):
        return False
    if bool(request.get("disable_classification")):
        return False
    return True
