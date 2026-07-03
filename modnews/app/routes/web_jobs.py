from __future__ import annotations

from flask import Blueprint, jsonify, request

from modnews.cli.local_client import LocalClient

bp = Blueprint("web_jobs", __name__)


@bp.get("/api/web-jobs")
def web_jobs():
    return jsonify({"items": LocalClient().web_jobs()})


@bp.get("/api/web-jobs/<job_id>")
def web_job(job_id: str):
    return jsonify({"item": LocalClient().web_job(job_id, include_events=True)})


@bp.get("/api/web-jobs/<job_id>/events")
def web_job_events(job_id: str):
    return jsonify({"items": LocalClient().web_job_events(job_id)})


@bp.post("/api/web-sources/<source_id>/run")
def run_web_source(source_id: str):
    return jsonify(LocalClient().web_source_run(source_id, request.get_json(silent=True) or {}))
