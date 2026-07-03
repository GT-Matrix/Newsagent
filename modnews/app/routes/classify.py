from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from modnews.app.context import local_client
from modnews.core.task import TaskEvent

bp = Blueprint("classify", __name__)


@bp.post("/api/classify/run")
def run_classify():
    payload = request.get_json(silent=True) or {}
    client = local_client()
    task_id = f"classify-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    task = TaskEvent(
        id=task_id,
        type="classify.clustered_pipeline",
        pipeline_run_id=payload.get("run_id"),
        step_id="classify/clustered_pipeline",
        payload={"project_root": str(client.project_root), **payload},
        concurrency_key="classify",
        max_concurrency=1,
    )
    client.container.event_queue.submit(task)
    task_payload = client.queue_show(task_id)
    return jsonify({"ok": task_payload.get("state") == "succeeded", "task": task_payload})
