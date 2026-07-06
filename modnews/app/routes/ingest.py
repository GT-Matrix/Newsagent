from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from modnews.app.context import local_client
from modnews.service.ingest.entrypoints import run_ingest_step_tasks

bp = Blueprint("ingest", __name__)


@bp.post("/api/ingest/run")
def run_ingest_step():
    payload = request.get_json(silent=True) or {}
    step_id = str(payload.get("step_id") or "")
    if step_id not in {"rss", "newsnow", "site_lists"}:
        return jsonify({"ok": False, "error": "invalid step_id"}), 400
    client = local_client()
    run_id = payload.get("run_id") or f"ingest-{step_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    if step_id == "site_lists":
        sites = payload.get("sites")
        if isinstance(sites, list):
            options["sites"] = [str(item) for item in sites if item]
        if payload.get("limit_per_site") is not None:
            options["limit_per_site"] = payload.get("limit_per_site")
        if payload.get("max_concurrency") is not None:
            options["max_concurrency"] = payload.get("max_concurrency")
    return jsonify(
        run_ingest_step_tasks(
            project_root=client.project_root,
            queue=client.container.event_queue,
            queue_show=client.queue_show,
            step_id=step_id,
            run_id=str(run_id),
            config_path=payload.get("config"),
            options=options,
        )
    )
