from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.cli.local_client import LocalClient

bp = Blueprint("runtime_config", __name__)


@bp.get("/api/runtime-config")
def runtime_config():
    return jsonify(LocalClient().config_show(include_paths=True))


@bp.get("/api/source-config")
def source_config():
    return jsonify(LocalClient().config_show())


@bp.patch("/api/runtime-config/steps/<step_id>")
def update_runtime_step(step_id: str):
    return jsonify({"ok": True, "config": LocalClient().config_update_step(step_id, request.get_json(silent=True) or {})})


@bp.patch("/api/runtime-config/classification")
def update_runtime_classification():
    return jsonify({"ok": True, "config": LocalClient().config_update_classification(request.get_json(silent=True) or {})})
