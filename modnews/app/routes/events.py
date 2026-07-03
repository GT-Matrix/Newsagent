from __future__ import annotations

from flask import Blueprint, Response, jsonify

from modnews.app.context import local_client

bp = Blueprint("events", __name__)


@bp.get("/api/state")
def state():
    return jsonify(local_client().state())


@bp.get("/api/events")
def events():
    return Response(local_client().event_stream(), mimetype="text/event-stream")
