from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.app.context import local_client

bp = Blueprint("extractors", __name__)


@bp.get("/api/extractors")
def list_extractors():
    return jsonify({"items": local_client().extractors_list()})


@bp.patch("/api/extractors/<source_id>")
def update_extractor(source_id: str):
    payload = request.get_json(silent=True) or {}
    return jsonify({"ok": True, "item": local_client().extractor_set_enabled(source_id, bool(payload.get("enabled")))})


@bp.delete("/api/extractors/<source_id>")
def delete_extractor(source_id: str):
    local_client().extractor_delete(source_id)
    return jsonify({"ok": True})
