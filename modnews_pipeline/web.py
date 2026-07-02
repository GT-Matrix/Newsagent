from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request

from .config import apply_runtime_overrides, load_config
from .extractors.registry import registry_from_project
from .extractors.repair import RepairManager
from .pipeline import run_pipeline
from .paths import runtime_paths
from .progress import BUS, emit, sse
from .sources import source_config_store
from .web_extraction.contract import WebSource
from .web_extraction.job_store import WebJobStore
from .web_extraction.orchestrator import WebExtractionOrchestrator


app = Flask(__name__)
_RUN_LOCK = threading.Lock()
_RUN_THREAD: threading.Thread | None = None


@app.get("/")
def index() -> Response:
    return jsonify(
        {
            "service": "modnews api",
            "ui": "Use the standalone Vite WebUI in /Users/zyf/Code/Projects/modnews_webUI.",
            "endpoints": ["/api/state", "/api/events", "/api/runtime-config", "/api/web-jobs", "/api/repair-tasks"],
        }
    )


@app.get("/api/state")
def state() -> Response:
    payload = BUS.snapshot()
    payload["outputs"] = _output_state()
    return jsonify(payload)


@app.get("/api/outputs")
def outputs() -> Response:
    return jsonify(_output_state())


@app.get("/api/source-config")
def source_config() -> Response:
    return jsonify(_source_config_store().load())


@app.get("/api/runtime-config")
def runtime_config() -> Response:
    payload = _source_config_store().load()
    payload["paths"] = _runtime_paths_payload()
    return jsonify(payload)


@app.patch("/api/runtime-config/steps/<step_id>")
def update_runtime_step(step_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    return jsonify({"ok": True, "config": _source_config_store().update_step(step_id, payload)})


@app.patch("/api/runtime-config/classification")
def update_runtime_classification() -> Response:
    payload = request.get_json(silent=True) or {}
    return jsonify({"ok": True, "config": _source_config_store().update_classification(payload)})


@app.patch("/api/runtime-config/paper-attach")
def update_runtime_paper_attach() -> Response:
    payload = request.get_json(silent=True) or {}
    return jsonify({"ok": True, "config": _source_config_store().update_paper_attach(payload)})


@app.put("/api/source-config/rss")
def update_rss_sources() -> Response:
    payload = request.get_json(silent=True) or {}
    items = payload.get("items")
    if not isinstance(items, list):
        return jsonify({"ok": False, "error": "items must be a list"}), 400
    return jsonify({"ok": True, "config": _source_config_store().update_rss(items)})


@app.put("/api/source-config/rss/<source_id>")
def update_rss_source(source_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    return jsonify({"ok": True, "config": _source_config_store().update_rss_item(source_id, payload)})


@app.delete("/api/source-config/rss/<source_id>")
def delete_rss_source(source_id: str) -> Response:
    return jsonify({"ok": True, "config": _source_config_store().delete_rss_item(source_id)})


@app.patch("/api/source-config/newsnow/<source_id>")
def update_newsnow_source(source_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    if not any(key in payload for key in ("enabled", "content_type")):
        return jsonify({"ok": False, "error": "enabled or content_type is required"}), 400
    return jsonify({"ok": True, "config": _source_config_store().update_newsnow_item(source_id, payload)})


@app.patch("/api/source-config/site-lists/<source_id>")
def update_site_list_source(source_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    return jsonify({"ok": True, "config": _source_config_store().update_site_list_item(source_id, payload)})


@app.put("/api/source-config/site-lists/<source_id>")
def upsert_site_list_source(source_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    if not payload.get("name") or not payload.get("url"):
        return jsonify({"ok": False, "error": "name and url are required"}), 400
    return jsonify({"ok": True, "config": _source_config_store().update_site_list_item(source_id, payload)})


@app.get("/api/web-jobs")
def web_jobs() -> Response:
    return jsonify({"items": _web_job_store().list()})


@app.get("/api/web-jobs/<job_id>")
def web_job(job_id: str) -> Response:
    try:
        return jsonify({"item": _web_job_store().get_dict(job_id, include_events=True)})
    except KeyError:
        return jsonify({"error": "not found"}), 404


@app.get("/api/web-jobs/<job_id>/events")
def web_job_events(job_id: str) -> Response:
    try:
        return jsonify({"items": _web_job_store().events(job_id)})
    except KeyError:
        return jsonify({"error": "not found"}), 404


@app.post("/api/web-sources/<source_id>/run")
def run_web_source(source_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    config = _source_config_store().load()
    raw = config.get("sources", {}).get("site_lists", {}).get(source_id)
    if not isinstance(raw, dict):
        return jsonify({"ok": False, "error": "source not found"}), 404
    source = WebSource.from_config(source_id, raw)
    if not source.enabled:
        return jsonify({"ok": False, "error": "source is disabled"}), 400
    limit = int(payload.get("limit") or config.get("steps", {}).get("site_lists", {}).get("limit_per_site", 10))
    scrape_date = str(payload.get("scrape_date") or datetime.now().astimezone().isoformat(timespec="seconds"))
    job = _web_orchestrator().run_source(source, scrape_date=scrape_date, limit=limit)
    emit("web_job_done", job_id=job.id, source_id=source_id, state=job.state, item_count=job.item_count)
    return jsonify({"ok": True, "item": job.to_dict()})


@app.get("/api/extractors")
def extractors() -> Response:
    registry = _extractor_registry()
    return jsonify({"items": [record.to_dict() for record in registry.list()]})


@app.patch("/api/extractors/<source_id>")
def update_extractor(source_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    registry = _extractor_registry()
    if "enabled" not in payload:
        return jsonify({"ok": False, "error": "enabled is required"}), 400
    record = registry.set_enabled(source_id, bool(payload["enabled"]))
    return jsonify({"ok": True, "item": record.to_dict()})


@app.delete("/api/extractors/<source_id>")
def delete_extractor(source_id: str) -> Response:
    _extractor_registry().delete(source_id)
    return jsonify({"ok": True})


@app.get("/api/repair-tasks")
def repair_tasks() -> Response:
    return jsonify({"items": _repair_manager().list_tasks()})


@app.get("/api/repair-tasks/<task_id>")
def repair_task(task_id: str) -> Response:
    try:
        return jsonify({"item": _repair_manager().get_task(task_id)})
    except KeyError:
        return jsonify({"error": "not found"}), 404


@app.post("/api/repair-tasks/<task_id>/retry")
def retry_repair_task(task_id: str) -> Response:
    try:
        task = _repair_manager().retry_task(task_id)
        emit("repair_task_retry", task_id=task.id, source_id=task.source_id, status=task.status)
        return jsonify({"ok": True, "item": task.to_dict()})
    except KeyError:
        return jsonify({"error": "not found"}), 404


@app.post("/api/repair-tasks/<task_id>/promote")
def promote_repair_task(task_id: str) -> Response:
    try:
        task = _repair_manager().promote_task(task_id)
        record = _extractor_registry().get(task.source_id)
        emit("repair_task_promoted", task_id=task.id, source_id=task.source_id, status=task.status)
        return jsonify({"ok": True, "item": task.to_dict(), "extractor": record.to_dict()})
    except KeyError:
        return jsonify({"error": "not found"}), 404
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.delete("/api/repair-tasks/<task_id>")
def delete_repair_task(task_id: str) -> Response:
    try:
        _repair_manager().delete_task(task_id)
        emit("repair_task_deleted", task_id=task_id)
        return jsonify({"ok": True})
    except KeyError:
        return jsonify({"error": "not found"}), 404


@app.post("/api/repair-tasks")
def create_repair_task() -> Response:
    payload = request.get_json(silent=True) or {}
    source_id = str(payload.get("source_id") or "").strip()
    if not source_id:
        return jsonify({"ok": False, "error": "source_id is required"}), 400
    extractor_id, metadata = _resolve_repair_source(source_id)
    task = _repair_manager().create_task(
        source_id=extractor_id,
        reason=str(payload.get("reason") or "manual repair request"),
        auto_start=bool(payload.get("auto_start", True)),
        source_metadata=metadata,
    )
    emit("repair_task_created", task_id=task.id, source_id=extractor_id, status=task.status)
    return jsonify({"ok": True, "item": task.to_dict()})


@app.post("/api/cache/clear")
def clear_cache() -> Response:
    config = load_config((request.get_json(silent=True) or {}).get("config"))
    removed = []
    for path in [config.classification.llm.cache_path, config.classification.embedding.cache_path]:
        if path and path.exists():
            path.unlink()
            removed.append(str(path))
            emit("cache_cleared", path=str(path))
    return jsonify({"ok": True, "removed": removed, "outputs": _output_state(config)})


@app.post("/api/run")
def run() -> Response:
    global _RUN_THREAD
    with _RUN_LOCK:
        if _RUN_THREAD and _RUN_THREAD.is_alive():
            return jsonify({"ok": False, "error": "pipeline is already running"}), 409
        payload = request.get_json(silent=True) or {}
        BUS.clear()
        _RUN_THREAD = threading.Thread(target=_run_pipeline_thread, args=(payload,), daemon=True)
        _RUN_THREAD.start()
    return jsonify({"ok": True})


@app.get("/api/events")
def events() -> Response:
    def stream():
        listener = BUS.listen()
        try:
            yield "retry: 1000\n\n"
            for event in BUS.snapshot()["events"]:
                yield f"event: replay\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            while True:
                yield sse(listener.get())
        finally:
            BUS.unlisten(listener)

    return Response(stream(), mimetype="text/event-stream")


def _run_pipeline_thread(payload: dict[str, Any]) -> None:
    global _RUN_THREAD
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    emit("pipeline_start", started_at=started_at, config_path=payload.get("config"))
    try:
        _load_runtime_env()
        config = load_config(payload.get("config"))
        if payload.get("resume_from_checkpoint"):
            config.classification.checkpoint_path = Path(payload["resume_from_checkpoint"]).resolve()
        news_mode = str(payload.get("news_mode") or os.environ.get("NEWS_MODE") or "")
        if news_mode:
            _apply_news_mode(config, news_mode)
        if payload.get("reset_classification", True):
            _reset_classification_outputs(config)
        apply_runtime_overrides(
            config,
            only_ingest_steps=payload.get("only_ingest_steps") or None,
            disable_classification=bool(payload.get("disable_classification")),
        )
        result = run_pipeline(config)
        emit(
            "pipeline_done",
            finished_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            output_path=str(result.output_path),
            stats={
                "total": len(result.items),
                "events": len(result.events),
                "classified": sum(1 for item in result.items if item.event_id),
            },
        )
    except Exception as exc:
        emit("pipeline_error", error=str(exc))
    finally:
        with _RUN_LOCK:
            if _RUN_THREAD is threading.current_thread():
                _RUN_THREAD = None


def _output_state(config: Any | None = None) -> dict[str, Any]:
    config = config or load_config()
    paths = {
        "news_with_events": config.classification.output_path,
        "events": config.classification.events_output_path,
        "discarded_news": config.classification.discarded_output_path,
        "checkpoint": config.classification.checkpoint_path,
        "llm_cache": config.classification.llm.cache_path,
        "embedding_cache": config.classification.embedding.cache_path,
    }
    result: dict[str, Any] = {}
    for key, path in paths.items():
        if not path:
            result[key] = {"path": None, "exists": False}
            continue
        info = {"path": str(path), "exists": path.exists()}
        if path.exists():
            info["size_bytes"] = path.stat().st_size
            if path.suffix == ".json":
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    info["count"] = len(data) if isinstance(data, list) else len(data.get("items", []))
                    if key == "checkpoint" and isinstance(data, dict):
                        info["meta"] = data.get("meta", {})
                except Exception as exc:
                    info["error"] = str(exc)
        result[key] = info
    return result


def _runtime_paths_payload() -> dict[str, str]:
    paths = runtime_paths(_project_root())
    return {
        "runtime_dir": str(paths.runtime_dir),
        "config_path": str(paths.config_path),
        "output_dir": str(paths.output_dir),
        "process_dir": str(paths.process_dir),
        "cache_dir": str(paths.cache_dir),
        "agent_work_dir": str(paths.agent_work_dir),
        "combined_news": str(paths.combined_news_path),
        "news_with_events": str(paths.news_with_events_path),
        "events": str(paths.events_path),
        "discarded_news": str(paths.discarded_news_path),
        "papers": str(paths.papers_path),
        "paper_attach_decisions": str(paths.paper_attach_decisions_path),
        "classification_checkpoint": str(paths.classification_checkpoint_path),
        "llm_cache": str(paths.llm_cache_path),
        "embedding_cache": str(paths.embedding_cache_path),
        "newsnow_cache_dir": str(paths.newsnow_cache_dir),
    }


def _apply_news_mode(config: Any, mode: str) -> None:
    if mode != "mock":
        return
    host = os.environ.get("MODNEWS_MOCK_HOST", "127.0.0.1")
    port = os.environ.get("MODNEWS_MOCK_PORT", "8123")
    _ensure_mock_server(host, port)
    base_url = f"http://{host}:{port}"
    config.newsnow_api_url = f"{base_url}/api/s"
    config.rss_api_url = f"{base_url}/api/rss"
    config.site_lists_api_url = f"{base_url}/api/site-lists"


def _ensure_mock_server(host: str, port: str) -> None:
    url = f"http://{host}:{port}/health"
    try:
        import requests

        requests.get(url, timeout=1).raise_for_status()
        return
    except Exception:
        pass

    script = Path(__file__).resolve().parents[2] / "scripts" / "run_mock_server.sh"
    subprocess.Popen(
        [str(script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    import requests

    for _ in range(20):
        try:
            requests.get(url, timeout=1).raise_for_status()
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"mock server failed to start at {url}")


def _load_runtime_env() -> None:
    env_file = Path(os.environ.get("MODNEWS_ENV_FILE", Path(__file__).resolve().parents[2] / ".env.runtime"))
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _reset_classification_outputs(config: Any) -> None:
    keep_names = {"llm_classification_cache.sqlite3", "event_vector_cache.sqlite3"}
    paths = [
        config.classification.output_path,
        config.classification.events_output_path,
        config.classification.discarded_output_path,
        config.classification.checkpoint_path,
    ]
    for path in paths:
        if path and path.exists() and path.name not in keep_names:
            path.unlink()
            emit("output_reset", path=str(path))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _extractor_registry():
    return registry_from_project(_project_root())


def _repair_manager() -> RepairManager:
    return RepairManager(_project_root(), _extractor_registry())


def _source_config_store():
    return source_config_store(_project_root())


def _web_job_store() -> WebJobStore:
    return WebJobStore(_project_root())


def _web_orchestrator() -> WebExtractionOrchestrator:
    return WebExtractionOrchestrator(_project_root())


def _resolve_repair_source(source_id: str) -> tuple[str, dict[str, Any]]:
    config = _source_config_store().load()
    web_sources = config.get("sources", {}).get("site_lists", {})
    raw = web_sources.get(source_id) if isinstance(web_sources, dict) else None
    if isinstance(raw, dict):
        extractor_id = str(raw.get("extractor_id") or source_id)
        return extractor_id, {"id": source_id, **raw}
    return source_id, {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the modnews API server.")
    parser.add_argument("--host", default=os.environ.get("MODNEWS_PROGRESS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MODNEWS_PROGRESS_PORT", "5055")))
    args = parser.parse_args()
    print(f"modnews api listening on http://{args.host}:{args.port}", flush=True)
    app.run(host=args.host, port=args.port, threaded=True)

if __name__ == "__main__":
    main()
