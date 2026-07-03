from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.cli.local_client import LocalClient

bp = Blueprint("pipeline", __name__)


@bp.post("/api/run")
def run():
    return jsonify(LocalClient().run_start(request.get_json(silent=True) or {}))


@bp.get("/api/runs")
def runs():
    return jsonify({"items": LocalClient().run_list()})


@bp.get("/api/runs/<run_id>")
def run_status(run_id: str):
    try:
        return jsonify({"item": LocalClient().run_status(run_id)})
    except KeyError:
        return jsonify({"error": "not found"}), 404
