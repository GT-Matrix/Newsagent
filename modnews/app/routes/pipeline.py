from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.app.context import local_client

bp = Blueprint("pipeline", __name__)


@bp.post("/api/run")
def run():
    return jsonify(local_client().run_start(request.get_json(silent=True) or {}))


@bp.get("/api/runs")
def runs():
    return jsonify({"items": local_client().run_list()})


@bp.get("/api/runs/<run_id>")
def run_status(run_id: str):
    try:
        return jsonify({"item": local_client().run_status(run_id)})
    except KeyError:
        return jsonify({"error": "not found"}), 404


@bp.post("/api/runs/<run_id>/resume")
def run_resume(run_id: str):
    try:
        return jsonify(local_client().run_resume(run_id))
    except KeyError:
        return jsonify({"ok": False, "error": "not found"}), 404


@bp.post("/api/runs/<run_id>/cancel")
def run_cancel(run_id: str):
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "cancelled by user")
    try:
        return jsonify(local_client().run_cancel(run_id, reason))
    except KeyError:
        return jsonify({"ok": False, "error": "not found"}), 404
