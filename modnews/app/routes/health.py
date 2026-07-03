from __future__ import annotations

from flask import Blueprint, jsonify

bp = Blueprint("health", __name__)


@bp.get("/")
def index():
    return jsonify(
        {
            "service": "modnews api",
            "endpoints": [
                "/api/state",
                "/api/events",
                "/api/runtime-config",
                "/api/web-jobs",
                "/api/repair-tasks",
            ],
        }
    )
