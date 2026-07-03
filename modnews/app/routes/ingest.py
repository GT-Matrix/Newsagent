from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from modnews.cli.local_client import LocalClient
from modnews.core.task import TaskEvent

bp = Blueprint("ingest", __name__)


@bp.post("/api/ingest/run")
def run_ingest_step():
    payload = request.get_json(silent=True) or {}
    step_id = str(payload.get("step_id") or "")
    if step_id not in {"rss", "newsnow", "site_lists"}:
        return jsonify({"ok": False, "error": "invalid step_id"}), 400
    client = LocalClient()
    task_id = f"ingest-{step_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    task = TaskEvent(
        id=task_id,
        type="ingest.run_step",
        pipeline_run_id=payload.get("run_id"),
        step_id=f"ingest/{step_id}",
        payload={"project_root": str(client.project_root), **payload, "step_id": step_id},
        concurrency_key=f"ingest:{step_id}",
        max_concurrency=1,
    )
    client.container.event_queue.dispatch(task)
    task_payload = client.queue_show(task_id)
    return jsonify({"ok": task_payload.get("state") == "succeeded", "task": task_payload})
