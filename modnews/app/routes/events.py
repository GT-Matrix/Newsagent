from __future__ import annotations

from flask import Blueprint, Response, jsonify

from modnews.cli.local_client import LocalClient

bp = Blueprint("events", __name__)


@bp.get("/api/state")
def state():
    return jsonify(LocalClient().state())


@bp.get("/api/events")
def events():
    return Response(LocalClient().event_stream(), mimetype="text/event-stream")
