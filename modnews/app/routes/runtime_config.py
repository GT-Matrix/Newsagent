from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.app.context import local_client

bp = Blueprint("runtime_config", __name__)


@bp.get("/api/runtime-config")
def runtime_config():
    return jsonify(local_client().config_show(include_paths=True))


@bp.get("/api/runtime/env-health")
def runtime_env_health():
    return jsonify(local_client().config_env_health())


@bp.get("/api/source-config")
def source_config():
    return jsonify(local_client().config_show())


@bp.get("/api/source-config/diagnostics")
def source_diagnostics():
    return jsonify(local_client().source_diagnostics())


@bp.post("/api/source-config/restore-builtins")
def restore_builtin_sources():
    return jsonify({"ok": True, "config": local_client().config_restore_builtins()})


@bp.patch("/api/runtime-config/steps/<step_id>")
def update_runtime_step(step_id: str):
    return jsonify({"ok": True, "config": local_client().config_update_step(step_id, request.get_json(silent=True) or {})})


@bp.patch("/api/runtime-config/classification")
def update_runtime_classification():
    return jsonify({"ok": True, "config": local_client().config_update_classification(request.get_json(silent=True) or {})})


@bp.put("/api/source-config/rss")
def update_rss_sources():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items")
    if not isinstance(items, list):
        return jsonify({"ok": False, "error": "items must be a list"}), 400
    return jsonify({"ok": True, "config": local_client().rss_update(items)})


@bp.put("/api/source-config/rss/<source_id>")
def update_rss_source(source_id: str):
    payload = request.get_json(silent=True) or {}
    current = next((row for row in local_client().sources_list("rss") if row.get("id") == source_id), {})
    merged = {**current, **payload, "id": source_id}
    return jsonify({"ok": True, "config": local_client().rss_update_item(source_id, merged)})


@bp.delete("/api/source-config/rss/<source_id>")
def delete_rss_source(source_id: str):
    return jsonify({"ok": True, "config": local_client().rss_delete_item(source_id)})


@bp.patch("/api/source-config/newsnow/<source_id>")
def update_newsnow_source(source_id: str):
    payload = request.get_json(silent=True) or {}
    if not any(key in payload for key in ("enabled", "content_type")):
        return jsonify({"ok": False, "error": "enabled or content_type is required"}), 400
    return jsonify({"ok": True, "config": local_client().newsnow_update_item(source_id, payload)})


@bp.patch("/api/source-config/site-lists/<source_id>")
def update_site_list_source(source_id: str):
    return jsonify({"ok": True, "config": local_client().site_list_update_item(source_id, request.get_json(silent=True) or {})})


@bp.put("/api/source-config/site-lists/<source_id>")
def upsert_site_list_source(source_id: str):
    payload = request.get_json(silent=True) or {}
    if not payload.get("name") or not payload.get("url"):
        return jsonify({"ok": False, "error": "name and url are required"}), 400
    return jsonify({"ok": True, "config": local_client().site_list_update_item(source_id, payload)})


@bp.delete("/api/source-config/site-lists/<source_id>")
def delete_site_list_source(source_id: str):
    return jsonify({"ok": True, "config": local_client().site_list_delete_item(source_id)})
