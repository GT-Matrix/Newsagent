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
from .pipeline import run_pipeline
from .progress import BUS, emit, sse


app = Flask(__name__)
_RUN_LOCK = threading.Lock()
_RUN_THREAD: threading.Thread | None = None


@app.get("/")
def index() -> str:
    return INDEX_HTML


@app.get("/api/state")
def state() -> Response:
    payload = BUS.snapshot()
    payload["outputs"] = _output_state()
    return jsonify(payload)


@app.get("/api/outputs")
def outputs() -> Response:
    return jsonify(_output_state())


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
    config.linux_do_api_url = f"{base_url}/api/linux-do"


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the modnews progress web UI.")
    parser.add_argument("--host", default=os.environ.get("MODNEWS_PROGRESS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MODNEWS_PROGRESS_PORT", "5055")))
    args = parser.parse_args()
    print(f"modnews progress listening on http://{args.host}:{args.port}", flush=True)
    app.run(host=args.host, port=args.port, threaded=True)


INDEX_HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Modnews Pipeline Progress</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d9dee7;
      --text: #1e2633;
      --muted: #667085;
      --accent: #0f766e;
      --warn: #b45309;
      --bad: #b42318;
      --good: #147a3c;
      --code: #101828;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      height: 54px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 3;
    }
    h1 { font-size: 16px; margin: 0; font-weight: 700; }
    button {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      border-radius: 6px;
      padding: 7px 10px;
      cursor: pointer;
    }
    button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 300px;
      min-height: calc(100vh - 54px);
    }
    .layout.sidebar-collapsed { grid-template-columns: minmax(0, 1fr) 42px; }
    main { min-width: 0; padding: 16px; }
    aside {
      border-left: 1px solid var(--line);
      background: var(--panel);
      padding: 14px;
      position: sticky;
      top: 54px;
      height: calc(100vh - 54px);
      overflow: auto;
    }
    .sidebar-collapsed aside .side-content { display: none; }
    .flow {
      display: flex;
      gap: 14px;
      overflow-x: auto;
      padding-bottom: 16px;
      align-items: flex-start;
    }
    .step {
      width: 390px;
      min-width: 390px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    .step-header {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: center;
    }
    .step-title { font-weight: 700; }
    .badge {
      border-radius: 999px;
      padding: 2px 8px;
      background: #eef2f6;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }
    .badge.running { color: #fff; background: var(--accent); }
    .badge.done { color: #fff; background: var(--good); }
    .badge.error { color: #fff; background: var(--bad); }
    .cards {
      max-height: calc(100vh - 150px);
      overflow: auto;
      padding: 8px;
    }
    .card {
      border: 1px solid var(--line);
      border-radius: 7px;
      margin-bottom: 8px;
      background: #fff;
    }
    .card summary {
      cursor: pointer;
      list-style: none;
      padding: 8px 10px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
    }
    .card summary::-webkit-details-marker { display: none; }
    .card-title {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 650;
    }
    .card-sub {
      grid-column: 1 / -1;
      color: var(--muted);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 12px;
    }
    .card-body {
      border-top: 1px solid var(--line);
      padding: 10px;
    }
    .label { color: var(--muted); font-size: 12px; margin-top: 8px; }
    pre {
      margin: 6px 0 0;
      padding: 8px;
      max-height: 260px;
      overflow: auto;
      background: #111827;
      color: #e5e7eb;
      border-radius: 6px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 12px;
    }
    .stream {
      background: #0b1220;
      color: #d1e7ff;
      min-height: 34px;
    }
    .stats {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 10px;
    }
    .stat {
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 8px;
    }
    .stat b { display: block; font-size: 18px; }
    .muted { color: var(--muted); }
    @media (max-width: 900px) {
      .layout, .layout.sidebar-collapsed { grid-template-columns: 1fr; }
      aside { position: static; height: auto; border-left: 0; border-top: 1px solid var(--line); }
      .step { width: 86vw; min-width: 86vw; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Modnews Pipeline Progress</h1>
    <div>
      <button id="toggleSide">统计</button>
      <button id="resumeBtn">从断点继续</button>
      <button id="mockRssBtn">Mock RSS</button>
      <button id="clearCacheBtn">清缓存</button>
      <button class="primary" id="runBtn">重跑分类</button>
    </div>
  </header>
  <div class="layout" id="layout">
    <main>
      <div class="flow" id="flow"></div>
    </main>
    <aside>
      <button id="collapseBtn">折叠</button>
      <div class="side-content">
        <h2 style="font-size:14px;margin:14px 0 6px;">总体统计</h2>
        <div class="muted" id="status">连接中</div>
        <div class="stats" id="stats"></div>
        <h2 style="font-size:14px;margin:16px 0 6px;">输出文件</h2>
        <pre id="outputs"></pre>
        <h2 style="font-size:14px;margin:16px 0 6px;">最近事件</h2>
        <pre id="recent"></pre>
      </div>
    </aside>
  </div>
  <script>
    const steps = [
      ["pipeline", "Pipeline"],
      ["start_checkpoint", "Checkpoint"],
      ["clustered_event_extraction", "标题聚类抽取"],
      ["clustered_event_merge", "事件聚类合并"],
      ["outputs", "输出"]
    ];
    const state = { stepStatus: {}, cards: new Map(), stats: {}, recent: [], outputs: {} };
    const flow = document.getElementById("flow");

    function init() {
      for (const [key, title] of steps) {
        const el = document.createElement("section");
        el.className = "step";
        el.id = `step-${key}`;
        el.innerHTML = `<div class="step-header"><div class="step-title">${title}</div><span class="badge" id="badge-${key}">idle</span></div><div class="cards" id="cards-${key}"></div>`;
        flow.appendChild(el);
      }
      fetch("/api/state").then(r => r.json()).then(payload => {
        (payload.events || []).forEach(applyEvent);
        state.stats = payload.stats || {};
        state.outputs = payload.outputs || {};
        renderStats();
        renderOutputs();
      });
      const es = new EventSource("/api/events");
      es.onmessage = e => applyEvent(JSON.parse(e.data));
      es.addEventListener("replay", e => applyEvent(JSON.parse(e.data)));
      ["pipeline_start","pipeline_done","pipeline_error","step_start","step_done","step_skip","checkpoint","output_reset","cache_cleared","llm_request_start","llm_stream_delta","llm_request_done","llm_cache_hit","llm_request_retry","llm_request_error","embedding_request_start","embedding_cache_hit","embedding_request_done","clustered_embedding_start","clustered_embedding_done","clustered_extraction_start","clustered_extraction_request","clustered_extraction_batch_done","clustered_extraction_done","clustered_merge_start","clustered_merge_request","clustered_merge_batch_done","clustered_merge_decision","clustered_merge_done"].forEach(type => {
        es.addEventListener(type, e => applyEvent(JSON.parse(e.data)));
      });
      es.onerror = () => document.getElementById("status").textContent = "SSE 断开，浏览器会自动重连";
    }

    function applyEvent(ev) {
      state.recent.push(`${new Date((ev.ts || Date.now()/1000)*1000).toLocaleTimeString()} ${ev.type}`);
      state.recent = state.recent.slice(-30);
      document.getElementById("recent").textContent = state.recent.join("\n");
      if (ev.type === "pipeline_start") setStep("pipeline", "running");
      if (ev.type === "pipeline_done") { setStep("pipeline", "done"); setStep("outputs", "done"); Object.assign(state.stats, ev.stats || {}); refreshOutputs(); }
      if (ev.type === "pipeline_error") {
        setStep("pipeline", "error");
        if (state.stats.current_step) setStep(state.stats.current_step, "error");
        refreshOutputs();
      }
      if (ev.type === "step_start") setStep(ev.step, "running");
      if (ev.type === "step_done") setStep(ev.step, "done");
      if (ev.type === "checkpoint") { Object.assign(state.stats, ev.meta || {}); refreshOutputs(); }
      if (ev.type === "output_reset") addInfoCard("pipeline", "清理分类产物", ev.path || "", ev);
      if (ev.type === "cache_cleared") { addInfoCard("pipeline", "清理缓存", ev.path || "", ev); refreshOutputs(); }
      if (ev.type === "llm_request_start") upsertLlmCard(ev, true);
      if (ev.type === "llm_stream_delta") appendStream(ev.request_id, ev.delta);
      if (ev.type === "llm_request_done") finishLlmCard(ev);
      if (ev.type === "llm_cache_hit") upsertCacheCard(ev);
      if (ev.type === "llm_request_retry" || ev.type === "llm_request_error") markCard(ev.request_id, ev.type, ev.error);
      if (ev.type === "embedding_request_start" || ev.type === "embedding_cache_hit") upsertEmbeddingCard(ev);
      if (ev.type === "embedding_request_done") finishEmbeddingCard(ev);
      if (ev.type === "clustered_embedding_start") addInfoCard(ev.target === "events" ? "clustered_event_merge" : "clustered_event_extraction", "Embedding 预计算开始", `${ev.item_count} 条，并发 ${ev.concurrency}`, ev);
      if (ev.type === "clustered_embedding_done") addInfoCard(ev.target === "events" ? "clustered_event_merge" : "clustered_event_extraction", "Embedding 预计算完成", `${ev.item_count} 条`, ev);
      if (ev.type === "clustered_extraction_start") addInfoCard("clustered_event_extraction", "标题聚类抽取开始", `${ev.item_count} 条，${ev.batch_count} 批，并发 ${ev.concurrency}`, ev);
      if (ev.type === "clustered_extraction_request") addInfoCard("clustered_event_extraction", `Batch ${ev.batch_index}/${ev.batch_count}`, (ev.items || []).map(x => x.title).slice(0, 2).join(" / "), ev);
      if (ev.type === "clustered_extraction_batch_done") addInfoCard("clustered_event_extraction", `Batch ${ev.batch_index} 完成`, "", ev);
      if (ev.type === "clustered_extraction_done") addInfoCard("clustered_event_extraction", "标题聚类抽取完成", `${ev.event_count} 个事件，${ev.discarded_count} 条疑似`, ev);
      if (ev.type === "clustered_merge_start") addInfoCard("clustered_event_merge", "事件聚类合并开始", `${ev.event_count} 个事件，${ev.batch_count} 批，并发 ${ev.concurrency}`, ev);
      if (ev.type === "clustered_merge_request") addInfoCard("clustered_event_merge", `Batch ${ev.batch_index}/${ev.batch_count}`, (ev.events || []).map(x => x.event_label).slice(0, 2).join(" / "), ev);
      if (ev.type === "clustered_merge_batch_done") addInfoCard("clustered_event_merge", `Batch ${ev.batch_index} 完成`, "", ev);
      if (ev.type === "clustered_merge_decision") addInfoCard("clustered_event_merge", "合并决策", `${ev.target_event_id}: ${(ev.source_event_ids || []).join(", ")}`, ev);
      if (ev.type === "clustered_merge_done") addInfoCard("clustered_event_merge", "事件聚类合并完成", `${ev.event_count} 个事件，合并 ${ev.merged_event_count}`, ev);
      renderStats();
    }

    function resetUi() {
      state.cards.clear();
      state.stats = {};
      state.recent = [];
      state.outputs = {};
      for (const [key] of steps) {
        document.getElementById(`cards-${key}`).innerHTML = "";
        setStep(key, "idle");
      }
      renderStats();
      renderOutputs();
    }

    function setStep(step, status) {
      const key = steps.some(x => x[0] === step) ? step : "pipeline";
      const badge = document.getElementById(`badge-${key}`);
      if (!badge) return;
      badge.textContent = status;
      badge.className = `badge ${status}`;
    }

    function stepForTask(task) {
      if (task === "batch_ai_relevance") return "batch_relevance";
      if (task === "suspect_article_review") return "suspect_handling";
      if (task === "event_membership") return "event_membership";
      if (task === "event_merge_group") return "event_merge";
      if (task === "clustered_event_extraction") return "clustered_event_extraction";
      if (task === "clustered_event_merge") return "clustered_event_merge";
      return "pipeline";
    }

    function upsertLlmCard(ev, open) {
      const step = stepForTask(ev.task);
      const card = createCard(step, ev.request_id, ev.name || ev.task, ev.goal || ev.summary || "", open);
      card.querySelector(".summaryText").textContent = ev.summary || "";
      card.querySelector(".payload").textContent = JSON.stringify(ev.payload || ev.messages || {}, null, 2);
      card.querySelector(".status").textContent = "running";
    }

    function upsertCacheCard(ev) {
      const step = stepForTask(ev.task);
      const card = createCard(step, ev.request_id, `${ev.name || ev.task} · cache`, ev.goal || "", false);
      card.querySelector(".summaryText").textContent = ev.summary || "";
      card.querySelector(".payload").textContent = JSON.stringify(ev.payload || {}, null, 2);
      card.querySelector(".response").textContent = JSON.stringify(ev.response || {}, null, 2);
      card.querySelector(".status").textContent = "cached";
    }

    function upsertEmbeddingCard(ev) {
      const step = ev.text_preview && ev.text_preview.includes("evt_") ? "clustered_event_merge" : "clustered_event_extraction";
      const card = createCard(step, ev.request_id, ev.type === "embedding_cache_hit" ? "Embedding · cache" : "Embedding", ev.text_preview || "", false);
      card.querySelector(".summaryText").textContent = ev.text_preview || "";
      card.querySelector(".payload").textContent = JSON.stringify(ev, null, 2);
      card.querySelector(".status").textContent = ev.type === "embedding_cache_hit" ? "cached" : "running";
    }

    function finishEmbeddingCard(ev) {
      const card = state.cards.get(ev.request_id);
      if (!card) return;
      card.querySelector(".status").textContent = ev.cached ? "cached done" : "done";
      card.querySelector(".response").textContent = JSON.stringify(ev, null, 2);
    }

    function appendStream(id, delta) {
      const card = state.cards.get(id);
      if (!card) return;
      const stream = card.querySelector(".stream");
      stream.textContent += delta;
      stream.scrollTop = stream.scrollHeight;
    }

    function finishLlmCard(ev) {
      const card = state.cards.get(ev.request_id);
      if (!card) return;
      card.querySelector(".status").textContent = "done";
      card.querySelector(".response").textContent = JSON.stringify(ev.response || {}, null, 2);
    }

    function markCard(id, status, message) {
      const card = state.cards.get(id);
      if (!card) return;
      card.querySelector(".status").textContent = status;
      card.querySelector(".error").textContent = message || "";
    }

    function addInfoCard(step, title, summary, payload) {
      const id = `${payload.type || title}-${payload.id || Math.random()}`;
      const card = createCard(step, id, title, summary, false);
      card.querySelector(".payload").textContent = JSON.stringify(payload, null, 2);
      card.querySelector(".status").textContent = payload.type || "event";
    }

    function createCard(step, id, title, goal, open) {
      if (state.cards.has(id)) return state.cards.get(id);
      const container = document.getElementById(`cards-${step}`) || document.getElementById("cards-pipeline");
      const details = document.createElement("details");
      details.className = "card";
      details.open = !!open;
      details.innerHTML = `
        <summary>
          <div class="card-title">${escapeHtml(title)}</div>
          <span class="badge status">new</span>
          <div class="card-sub">${escapeHtml(goal || "")}</div>
        </summary>
        <div class="card-body">
          <div class="label">核心信息</div>
          <div class="summaryText muted"></div>
          <div class="label">结构化 Payload</div>
          <pre class="payload"></pre>
          <div class="label">LLM 流式输出</div>
          <pre class="stream"></pre>
          <div class="label">最终响应</div>
          <pre class="response"></pre>
          <pre class="error" style="color:#fecaca"></pre>
        </div>`;
      container.prepend(details);
      state.cards.set(id, details);
      return details;
    }

    function renderStats() {
      document.getElementById("status").textContent = state.stats.status || state.stats.stage || "ready";
      const stats = document.getElementById("stats");
      const rows = [
        ["总新闻", state.stats.total ?? state.stats.item_count],
        ["已分类", state.stats.classified],
        ["事件", state.stats.events ?? state.stats.event_count],
        ["疑似", state.stats.discarded_count],
        ["当前步骤", state.stats.current_step || state.stats.last_step],
        ["合并", state.stats.merged_event_count]
      ];
      stats.innerHTML = rows.map(([k,v]) => `<div class="stat"><span class="muted">${k}</span><b>${v ?? ""}</b></div>`).join("");
    }

    function renderOutputs() {
      const rows = Object.entries(state.outputs || {}).map(([key, info]) => {
        const count = info.count == null ? "" : ` count=${info.count}`;
        const size = info.size_bytes == null ? "" : ` size=${Math.round(info.size_bytes / 1024)}KB`;
        return `${key}: ${info.exists ? "ok" : "missing"}${count}${size}\n${info.path || ""}`;
      });
      document.getElementById("outputs").textContent = rows.join("\n\n");
    }

    function refreshOutputs() {
      fetch("/api/outputs").then(r => r.json()).then(payload => {
        state.outputs = payload || {};
        renderOutputs();
      });
    }

    function escapeHtml(text) {
      return String(text || "").replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
    }

    document.getElementById("runBtn").onclick = () => {
      startRun({reset_classification:true});
    };
    document.getElementById("mockRssBtn").onclick = () => {
      startRun({reset_classification:true, news_mode:"mock", only_ingest_steps:["rss"]});
    };
    document.getElementById("resumeBtn").onclick = () => {
      startRun({reset_classification:false});
    };
    document.getElementById("clearCacheBtn").onclick = () => {
      fetch("/api/cache/clear", {method:"POST", headers:{"Content-Type":"application/json"}, body:"{}"})
        .then(r => r.json()).then(payload => {
          state.outputs = payload.outputs || {};
          renderOutputs();
          if (!payload.ok) alert(payload.error || "清理失败");
        });
    };
    function startRun(payload) {
      resetUi();
      fetch("/api/run", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)})
        .then(r => r.json()).then(payload => {
          if (!payload.ok) {
            document.getElementById("status").textContent = payload.error || "启动失败";
            alert(payload.error || "启动失败");
          }
        });
    }
    document.getElementById("collapseBtn").onclick = document.getElementById("toggleSide").onclick = () => {
      document.getElementById("layout").classList.toggle("sidebar-collapsed");
    };
    init();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
