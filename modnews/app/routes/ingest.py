from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from modnews.app.context import local_client
from modnews.service.ingest.planner import plan_ingest_tasks

bp = Blueprint("ingest", __name__)


@bp.post("/api/ingest/run")
def run_ingest_step():
    payload = request.get_json(silent=True) or {}
    step_id = str(payload.get("step_id") or "")
    if step_id not in {"rss", "newsnow", "site_lists"}:
        return jsonify({"ok": False, "error": "invalid step_id"}), 400
    client = local_client()
    run_id = payload.get("run_id") or f"ingest-{step_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    tasks = plan_ingest_tasks(
        project_root=client.project_root,
        step_id=step_id,
        run_id=str(run_id),
    )
    for task in tasks:
        client.container.event_queue.register(task)
    client.container.event_queue.drain_ready()
    task_payloads = [client.queue_show(task.id) for task in tasks]
    return jsonify({"ok": all(task.get("state") == "succeeded" for task in task_payloads), "tasks": task_payloads})
