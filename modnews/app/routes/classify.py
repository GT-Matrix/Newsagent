from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.app.context import local_client
from modnews.service.classify.entrypoints import run_classify_tasks

bp = Blueprint("classify", __name__)


@bp.post("/api/classify/run")
def run_classify():
    payload = request.get_json(silent=True) or {}
    client = local_client()
    return jsonify(
        run_classify_tasks(
            project_root=client.project_root,
            queue=client.container.event_queue,
            queue_show=client.queue_show,
            run_id=payload.get("run_id"),
            input_path=payload.get("input_path") or payload.get("input"),
            config=payload.get("config"),
            pipeline_descriptors=client.container.pipeline_manager.describe_steps(),
        )
    )
