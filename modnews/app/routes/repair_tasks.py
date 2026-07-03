from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.cli.local_client import LocalClient

bp = Blueprint("repair_tasks", __name__)


@bp.get("/api/repair-tasks")
def repair_tasks():
    return jsonify({"items": LocalClient().repair_tasks()})


@bp.get("/api/repair-tasks/<task_id>")
def repair_task(task_id: str):
    return jsonify({"item": LocalClient().repair_task(task_id)})


@bp.post("/api/repair-tasks")
def create_repair_task():
    return jsonify(LocalClient().repair_create(request.get_json(silent=True) or {}))


@bp.post("/api/repair-tasks/<task_id>/retry")
def retry_repair_task(task_id: str):
    return jsonify(LocalClient().repair_retry(task_id))


@bp.post("/api/repair-tasks/<task_id>/promote")
def promote_repair_task(task_id: str):
    return jsonify(LocalClient().repair_promote(task_id))


@bp.delete("/api/repair-tasks/<task_id>")
def delete_repair_task(task_id: str):
    return jsonify(LocalClient().repair_delete(task_id))
