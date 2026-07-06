from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from modnews.app.context import local_client
from modnews.service.ingest.registry import default_ingest_registry
from modnews.service.ingest.entrypoints import run_ingest_step_tasks

bp = Blueprint("ingest", __name__)


@bp.post("/api/ingest/run")
def run_ingest_step():
    payload = request.get_json(silent=True) or {}
    step_id = str(payload.get("step_id") or "")
    registry = default_ingest_registry()
    if step_id not in registry.list():
        return jsonify({"ok": False, "error": "invalid step_id"}), 400
    step_cls = registry.get(step_id)
    client = local_client()
    run_id = payload.get("run_id") or f"ingest-{step_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    options = step_cls.options_from_api_payload(payload)
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
