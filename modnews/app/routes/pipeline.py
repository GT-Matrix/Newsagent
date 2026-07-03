from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.cli.local_client import LocalClient

bp = Blueprint("pipeline", __name__)


@bp.post("/api/run")
def run():
    return jsonify(LocalClient().run_start(request.get_json(silent=True) or {}))
