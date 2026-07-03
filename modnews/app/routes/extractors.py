from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.cli.local_client import LocalClient

bp = Blueprint("extractors", __name__)


@bp.get("/api/extractors")
def list_extractors():
    return jsonify({"items": LocalClient().extractors_list()})


@bp.patch("/api/extractors/<source_id>")
def update_extractor(source_id: str):
    payload = request.get_json(silent=True) or {}
    return jsonify({"ok": True, "item": LocalClient().extractor_set_enabled(source_id, bool(payload.get("enabled")))})


@bp.delete("/api/extractors/<source_id>")
def delete_extractor(source_id: str):
    LocalClient().extractor_delete(source_id)
    return jsonify({"ok": True})
