from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.app.context import local_client

bp = Blueprint("runtime", __name__)


@bp.get("/api/outputs")
def outputs():
    return jsonify(local_client().outputs_status())


@bp.get("/api/outputs/<key>/content")
def output_content(key: str):
    try:
        return jsonify(local_client().outputs_cat(key))
    except KeyError:
        return jsonify({"ok": False, "error": "unknown output key"}), 404
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "artifact not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.get("/api/queue")
def queue_list():
    states = {item for item in request.args.get("state", "").split(",") if item}
    return jsonify({"items": local_client().queue_list(states or None)})


@bp.get("/api/queue/status")
def queue_status():
    return jsonify(local_client().queue_status())


@bp.get("/api/queue/<task_id>")
def queue_show(task_id: str):
    return jsonify(local_client().queue_show(task_id))


@bp.post("/api/queue/echo")
def queue_echo():
    payload = request.get_json(silent=True) or {}
    task_id = str(payload.get("task_id") or "diagnostic-echo")
    return jsonify(local_client().queue_echo(task_id, payload.get("payload") if isinstance(payload.get("payload"), dict) else {}))


@bp.post("/api/queue/drain")
def queue_drain():
    payload = request.get_json(silent=True) or {}
    limit = payload.get("limit")
    if limit is not None:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    return jsonify(local_client().queue_drain(limit))


@bp.post("/api/queue/<task_id>/cancel")
def queue_cancel(task_id: str):
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "cancelled by user")
    try:
        return jsonify(local_client().queue_cancel(task_id, reason))
    except KeyError:
        return jsonify({"ok": False, "error": "not found"}), 404


@bp.post("/api/queue/<task_id>/retry")
def queue_retry(task_id: str):
    try:
        return jsonify(local_client().queue_retry(task_id))
    except KeyError:
        return jsonify({"ok": False, "error": "not found"}), 404


@bp.post("/api/queue/<task_id>/skip")
def queue_skip(task_id: str):
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "skipped by user")
    try:
        return jsonify(local_client().queue_skip(task_id, reason))
    except KeyError:
        return jsonify({"ok": False, "error": "not found"}), 404


@bp.get("/api/cache")
def cache_status():
    return jsonify(local_client().cache_status())


@bp.post("/api/cache/clear")
def cache_clear():
    payload = request.get_json(silent=True) or {}
    clear_llm = bool(payload.get("llm", True))
    clear_embedding = bool(payload.get("embedding", True))
    return jsonify(local_client().cache_clear(llm=clear_llm, embedding=clear_embedding))


@bp.get("/api/checkpoints")
def checkpoints():
    return jsonify({"items": local_client().checkpoints_list(request.args.get("run"))})


@bp.post("/api/checkpoints/publish")
def publish_checkpoint():
    payload = request.get_json(silent=True) or {}
    checkpoint_path = str(payload.get("checkpoint_path") or "")
    if not checkpoint_path:
        return jsonify({"ok": False, "error": "checkpoint_path is required"}), 400
    try:
        return jsonify(local_client().checkpoint_publish(checkpoint_path))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
