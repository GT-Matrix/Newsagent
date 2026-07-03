from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.app.context import local_client
from modnews.service.classify.planner import plan_clustered_classify_tasks

bp = Blueprint("classify", __name__)


@bp.post("/api/classify/run")
def run_classify():
    payload = request.get_json(silent=True) or {}
    client = local_client()
    tasks = plan_clustered_classify_tasks(
        project_root=client.project_root,
        run_id=payload.get("run_id"),
        input_path=payload.get("input_path") or payload.get("input"),
        config=payload.get("config"),
    )
    for task in tasks:
        client.container.event_queue.register(task)
    client.container.event_queue.drain_ready()
    task_payloads = [client.queue_show(task.id) for task in tasks]
    return jsonify({"ok": all(task.get("state") == "succeeded" for task in task_payloads), "tasks": task_payloads})
