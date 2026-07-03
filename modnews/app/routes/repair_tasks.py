from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.app.context import local_client

bp = Blueprint("repair_tasks", __name__)


@bp.get("/api/repair-tasks")
def repair_tasks():
    return jsonify({"items": local_client().repair_tasks()})


@bp.get("/api/repair-tasks/<task_id>")
def repair_task(task_id: str):
    return jsonify({"item": local_client().repair_task(task_id)})


@bp.post("/api/repair-tasks")
def create_repair_task():
    return jsonify(local_client().repair_create(request.get_json(silent=True) or {}))


@bp.post("/api/repair-tasks/<task_id>/retry")
def retry_repair_task(task_id: str):
    return jsonify(local_client().repair_retry(task_id))


@bp.post("/api/repair-tasks/<task_id>/promote")
def promote_repair_task(task_id: str):
    return jsonify(local_client().repair_promote(task_id))


@bp.delete("/api/repair-tasks/<task_id>")
def delete_repair_task(task_id: str):
    return jsonify(local_client().repair_delete(task_id))
