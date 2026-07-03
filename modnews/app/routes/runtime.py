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


@bp.get("/api/cache")
def cache_status():
    return jsonify(LocalClient().cache_status())


@bp.post("/api/cache/clear")
def cache_clear():
    payload = request.get_json(silent=True) or {}
    return jsonify(LocalClient().cache_clear(llm=bool(payload.get("llm")), embedding=bool(payload.get("embedding"))))


@bp.get("/api/checkpoints")
def checkpoints():
    return jsonify({"items": LocalClient().checkpoints_list(request.args.get("run"))})
