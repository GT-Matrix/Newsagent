from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.cli.local_client import LocalClient

bp = Blueprint("runtime", __name__)


@bp.get("/api/outputs")
def outputs():
    return jsonify(LocalClient().outputs_status())


@bp.get("/api/queue")
def queue_list():
    states = {item for item in request.args.get("state", "").split(",") if item}
    return jsonify({"items": LocalClient().queue_list(states or None)})


@bp.get("/api/queue/status")
def queue_status():
    return jsonify(LocalClient().queue_status())


@bp.get("/api/queue/<task_id>")
def queue_show(task_id: str):
    return jsonify(LocalClient().queue_show(task_id))


@bp.post("/api/queue/echo")
def queue_echo():
    payload = request.get_json(silent=True) or {}
    task_id = str(payload.get("task_id") or "diagnostic-echo")
    return jsonify(LocalClient().queue_echo(task_id, payload.get("payload") if isinstance(payload.get("payload"), dict) else {}))


@bp.get("/api/cache")
def cache_status():
    return jsonify(LocalClient().cache_status())


@bp.post("/api/cache/clear")
def cache_clear():
    payload = request.get_json(silent=True) or {}
    clear_llm = bool(payload.get("llm", True))
    clear_embedding = bool(payload.get("embedding", True))
    return jsonify(LocalClient().cache_clear(llm=clear_llm, embedding=clear_embedding))


@bp.get("/api/checkpoints")
def checkpoints():
    return jsonify({"items": LocalClient().checkpoints_list(request.args.get("run"))})
