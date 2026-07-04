from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, request

from modnews.app.context import local_client
from modnews.service.report import generate_report

bp = Blueprint("report", __name__)


@bp.post("/api/report/generate")
def generate():
    payload = request.get_json(silent=True) or {}
    project_root = local_client().project_root
    raw_input = payload.get("input") or payload.get("input_path")
    if not raw_input:
        return jsonify({"ok": False, "error": "input is required"}), 400
    input_path = Path(str(raw_input)).expanduser()
    if not input_path.is_absolute():
        input_path = (project_root / input_path).resolve()
    raw_output = payload.get("output_dir")
    output_dir = Path(str(raw_output)).expanduser() if raw_output else (project_root / "data" / "output")
    if not output_dir.is_absolute():
        output_dir = (project_root / output_dir).resolve()
    config_path = None
    if payload.get("config"):
        config_path = Path(str(payload["config"])).expanduser()
        if not config_path.is_absolute():
            config_path = (project_root / config_path).resolve()
    events = generate_report(
        input_path,
        output_dir,
        report_date=payload.get("date"),
        config_path=config_path,
    )
    selected = [event for event in events if event.should_include_report]
    with_sources = [event for event in events if event.source_items]
    return jsonify(
        {
            "ok": True,
            "event_count": len(events),
            "events_with_sources": len(with_sources),
            "selected_count": len(selected),
            "output_dir": str(output_dir),
        }
    )
