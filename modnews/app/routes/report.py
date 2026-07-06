from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.app.context import local_client
from modnews.service.report.entrypoints import run_report_tasks

bp = Blueprint("report", __name__)


@bp.post("/api/report/generate")
def generate():
    payload = request.get_json(silent=True) or {}
    raw_input = payload.get("input") or payload.get("input_path")
    if not raw_input:
        return jsonify({"ok": False, "error": "input is required"}), 400
    client = local_client()
    result = run_report_tasks(
        project_root=client.project_root,
        queue=client.container.event_queue,
        queue_show=client.queue_show,
        input_path=str(raw_input),
        output_dir=payload.get("output_dir"),
        date=payload.get("date"),
        config=payload.get("config"),
        run_id=payload.get("run_id"),
    )
    return jsonify(result)
