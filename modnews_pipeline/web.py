
from __future__ import annotations

import argparse
import json
import os
import threading
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
    return jsonify(BUS.snapshot())

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
    config_path = payload.get("config") or "config.local.json"
    emit("pipeline_start", started_at=datetime.now().astimezone().isoformat(timespec="seconds"), config_path=config_path)
    try:
        config = load_config(config_path)
        if payload.get("resume_from_checkpoint"):
            config.classification.checkpoint_path = Path(payload["resume_from_checkpoint"]).resolve()
        if payload.get("reset_classification", True):
            _reset_classification_outputs(config)
        apply_runtime_overrides(config, only_ingest_steps=payload.get("only_ingest_steps") or None, disable_classification=bool(payload.get("disable_classification")))
        result = run_pipeline(config)
        emit("pipeline_done", finished_at=datetime.now().astimezone().isoformat(timespec="seconds"), output_path=str(result.output_path), stats={"total": len(result.items), "events": len(result.events), "classified": sum(1 for item in result.items if item.event_id)})
    except Exception as exc:
        emit("pipeline_error", error=f"{type(exc).__name__}: {exc}")

def _reset_classification_outputs(config: Any) -> None:
    keep_names = {"llm_classification_cache.sqlite3", "event_vector_cache.sqlite3"}
    for path in [config.classification.output_path, config.classification.events_output_path, config.classification.discarded_output_path, config.classification.checkpoint_path]:
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
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Modnews Console</title><style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#111827;--panel2:#172033;--line:#2b364a;--text:#e5e7eb;--muted:#93a4b8;--green:#22c55e;--blue:#38bdf8;--red:#ef4444}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.top{height:60px;display:flex;align-items:center;justify-content:space-between;padding:0 18px;border-bottom:1px solid var(--line);background:#090f1d;position:sticky;top:0;z-index:5}.brand{display:flex;gap:10px;align-items:center}.logo{width:28px;height:28px;border-radius:7px;background:linear-gradient(135deg,var(--green),var(--blue))}.brand b{display:block;font-size:16px}.brand span{display:block;color:var(--muted);font-size:12px}.actions{display:flex;gap:8px;align-items:center}input,button{height:34px;border-radius:6px;border:1px solid var(--line);background:#101827;color:var(--text);padding:0 10px;font:inherit}input{width:220px}button{cursor:pointer}button:hover{border-color:var(--blue)}button.primary{background:var(--green);border-color:var(--green);color:#04130a;font-weight:700}.summary{display:grid;grid-template-columns:1.4fr repeat(4,1fr);gap:12px;padding:14px 18px;border-bottom:1px solid var(--line);background:#0d1424}.status,.metric{border:1px solid var(--line);background:var(--panel);border-radius:8px;padding:12px}.run{display:flex;gap:9px;align-items:center;font-weight:700}.dot{width:10px;height:10px;border-radius:50%;background:var(--muted)}.dot.running{background:var(--blue);animation:pulse 1.2s infinite}.dot.done{background:var(--green)}.dot.error{background:var(--red)}@keyframes pulse{to{box-shadow:0 0 0 9px rgba(56,189,248,0)}}.current{margin-top:8px;color:var(--muted);min-height:20px}.metric span{color:var(--muted);font-size:12px}.metric b{display:block;font-size:23px;margin-top:4px}.main{display:grid;grid-template-columns:250px minmax(0,1fr) 340px;min-height:calc(100vh - 150px)}.rail,.side{background:#090f1d;padding:14px;overflow:auto}.rail{border-right:1px solid var(--line)}.side{border-left:1px solid var(--line)}.phases{display:grid;gap:8px}.phase{display:grid;grid-template-columns:24px 1fr auto;align-items:center;gap:8px;border:1px solid var(--line);background:#101827;border-radius:8px;padding:9px;color:var(--muted)}.phase i{font-style:normal;width:24px;height:24px;border-radius:50%;background:#1f2937;display:grid;place-items:center;font-size:12px}.phase b{color:var(--text)}.phase.running{border-color:var(--blue);color:#bae6fd;background:#102238}.phase.done{border-color:rgba(34,197,94,.6);color:#bbf7d0}.phase.error{border-color:var(--red);color:#fecaca}
.work{padding:14px;overflow:auto}.board{display:grid;grid-template-columns:repeat(2,minmax(330px,1fr));gap:12px}.step{background:var(--panel);border:1px solid var(--line);border-radius:8px;min-height:180px;overflow:hidden}.step.running{border-color:var(--blue)}.step.done{border-color:rgba(34,197,94,.6)}.step.error{border-color:var(--red)}.stepHead{height:42px;background:var(--panel2);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 12px;font-weight:700}.badge{border:1px solid var(--line);border-radius:999px;padding:2px 8px;color:var(--muted);font-size:12px;font-weight:400}.badge.running{border-color:var(--blue);color:#bae6fd}.badge.done,.badge.cached{border-color:var(--green);color:#bbf7d0}.badge.error,.badge.llm_request_error{border-color:var(--red);color:#fecaca}.cards{display:grid;gap:9px;padding:10px}.empty{color:var(--muted);border:1px dashed var(--line);border-radius:8px;padding:24px;text-align:center;background:#0d1424}.card{border:1px solid var(--line);background:#0d1424;border-radius:7px;overflow:hidden}.card summary{list-style:none;cursor:pointer;padding:9px}.cardTop{display:flex;justify-content:space-between;gap:8px}.title{font-weight:650;word-break:break-word}.sub{color:var(--muted);font-size:12px;margin-top:3px;word-break:break-word}.body{padding:0 9px 9px}.label{margin-top:8px;color:var(--muted);font-size:12px}pre{margin:5px 0 0;padding:8px;background:#070c16;border:1px solid #1b2638;border-radius:6px;max-height:180px;overflow:auto;white-space:pre-wrap;word-break:break-word;color:#dbeafe;font-size:12px}.stats{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px}.stat{border:1px solid var(--line);background:#101827;border-radius:8px;padding:9px}.stat span{color:var(--muted);font-size:12px}.stat b{display:block;font-size:18px}.side h2{font-size:13px;margin:0 0 8px}@media(max-width:1180px){.summary{grid-template-columns:1fr 1fr}.main{grid-template-columns:220px 1fr}.side{grid-column:1/-1;border-left:0;border-top:1px solid var(--line)}.board{grid-template-columns:1fr}}@media(max-width:760px){.top{height:auto;display:block;padding:12px}.actions{margin-top:10px;flex-wrap:wrap}.summary,.main{grid-template-columns:1fr}.rail{border-right:0;border-bottom:1px solid var(--line)}input{width:100%}.board{grid-template-columns:1fr}}
</style></head><body><div class="top"><div class="brand"><div class="logo"></div><div><b>Modnews Pipeline Console</b><span>&#37319;&#38598; / &#36807;&#28388; / &#32858;&#31867; / &#20998;&#31867;&#36827;&#24230;</span></div></div><div class="actions"><input id="configPath" value="config.local.json"><button id="resumeBtn">&#20174;&#26029;&#28857;&#32487;&#32493;</button><button id="runBtn" class="primary">&#37325;&#36305;&#20998;&#31867;</button></div></div><section class="summary"><div class="status"><div class="run"><span id="runDot" class="dot"></span><span id="runText">&#26410;&#36816;&#34892;</span></div><div id="currentText" class="current">&#25171;&#24320;&#39029;&#38754;&#19981;&#20250;&#33258;&#21160;&#36305;&#65292;&#28857;&#20987;&#21491;&#19978;&#35282;&#25353;&#38062;&#24320;&#22987;&#12290;</div></div><div class="metric"><span>&#32791;&#26102;</span><b id="elapsed">00:00</b></div><div class="metric"><span>&#20107;&#20214;</span><b id="eventCount">0</b></div><div class="metric"><span>LLM</span><b id="llmCount">0</b></div><div class="metric"><span>&#38169;&#35823;</span><b id="errorCount">0</b></div></section><div class="main"><aside class="rail"><div class="phases" id="phaseList"></div></aside><main class="work"><div class="board" id="board"></div></main><aside class="side"><h2>&#24635;&#20307;&#32479;&#35745;</h2><div id="stats" class="stats"></div><h2>&#26368;&#36817;&#20107;&#20214;</h2><pre id="recent"></pre></aside></div><script>
const T={ingest:"\u6570\u636e\u6293\u53d6",classification:"\u5206\u7c7b\u603b\u9636\u6bb5",start_checkpoint:"Checkpoint",batch_relevance:"\u6279\u91cf\u76f8\u5173\u6027",suspect_handling:"\u7591\u4f3c\u5904\u7406",event_membership:"\u4e8b\u4ef6\u5f52\u5e76",event_merge:"\u4e8b\u4ef6\u5408\u5e76",outputs:"\u8f93\u51fa",pipeline:"Pipeline",total:"\u603b\u65b0\u95fb",classified:"\u5df2\u5206\u7c7b",events:"\u4e8b\u4ef6",discarded:"\u4e22\u5f03",progress:"\u5019\u9009\u8fdb\u5ea6",merged:"\u5408\u5e76"};
const steps=[["pipeline",T.pipeline],["ingest",T.ingest],["classification",T.classification],["start_checkpoint",T.start_checkpoint],["batch_relevance",T.batch_relevance],["suspect_handling",T.suspect_handling],["event_membership",T.event_membership],["event_merge",T.event_merge],["outputs",T.outputs]],ingestSources=new Set(["rss","newsnow","linux_do","site_lists"]),state={cards:new Map(),stats:{},recent:[],eventCount:0,llmCount:0,errorCount:0,startMs:null,timer:null};
function init(){steps.forEach(([k,t],i)=>{phaseList.insertAdjacentHTML("beforeend",`<div class="phase" id="phase-${k}"><i>${i+1}</i><b>${t}</b><span id="phase-status-${k}">idle</span></div>`);board.insertAdjacentHTML("beforeend",`<section class="step" id="step-${k}"><div class="stepHead"><span>${t}</span><span class="badge" id="badge-${k}">idle</span></div><div class="cards" id="cards-${k}"><div class="empty">Waiting for events</div></div></section>`)});fetch("/api/state").then(r=>r.json()).then(p=>{(p.events||[]).forEach(applyEvent);state.stats=p.stats||{};renderStats();renderTop()});const es=new EventSource("/api/events");es.onmessage=e=>applyEvent(JSON.parse(e.data));es.addEventListener("replay",e=>applyEvent(JSON.parse(e.data)));["pipeline_start","pipeline_done","pipeline_error","step_start","step_done","step_skip","checkpoint","output_reset","ingest_source_start","ingest_source_done","llm_request_start","llm_stream_delta","llm_request_done","llm_cache_hit","llm_request_retry","llm_request_error","embedding_request_start","embedding_cache_hit","embedding_request_done","membership_candidates","membership_decision","merge_candidates","merge_decision","merge_round_start","merge_round_done","batch_relevance_start","batch_relevance_request","batch_relevance_done"].forEach(x=>es.addEventListener(x,e=>applyEvent(JSON.parse(e.data))))}
function applyEvent(ev){state.eventCount++;if(ev.type==="llm_request_start"||ev.type==="llm_cache_hit")state.llmCount++;if((ev.type||"").includes("error"))state.errorCount++;state.recent.push(`${new Date((ev.ts||Date.now()/1000)*1000).toLocaleTimeString()} ${ev.type}`);state.recent=state.recent.slice(-40);recent.textContent=state.recent.join("\n");if(ev.type==="pipeline_start"){state.startMs=Date.now();timer();run("running","\u8fd0\u884c\u4e2d");step("pipeline","running");cur(`\u5df2\u542f\u52a8\uff1a${ev.config_path||"config.local.json"}`)}if(ev.type==="pipeline_done"){run("done","\u5df2\u5b8c\u6210");step("pipeline","done");step("outputs","done");Object.assign(state.stats,ev.stats||{});cur(`\u5b8c\u6210\uff1a${ev.output_path||""}`);clearInterval(state.timer)}if(ev.type==="pipeline_error"){run("error","\u51fa\u9519");step("pipeline","error");card("pipeline","Pipeline error",ev.error||"",ev,true);cur(ev.error||"error");clearInterval(state.timer)}if(ev.type==="step_start"){let s=norm(ev.step);step(s,"running");cur(`\u6b63\u5728\u6267\u884c\uff1a${T[s]||s}`)}if(ev.type==="step_done"){let s=norm(ev.step);step(s,"done");if(ev.item_count!=null)state.stats.item_count=ev.item_count;if(ev.event_count!=null)state.stats.event_count=ev.event_count}if(ev.type==="checkpoint")Object.assign(state.stats,ev.meta||{});if(ev.type==="ingest_source_start"){step("ingest","running");card("ingest",`\u5f00\u59cb\u6293\u53d6 ${ev.source}`,"",ev,true);cur(`\u6b63\u5728\u6293\u53d6\uff1a${ev.source}`)}if(ev.type==="ingest_source_done"){card("ingest",`\u5b8c\u6210\u6293\u53d6 ${ev.source}`,`${ev.item_count||0} \u6761`,ev)}if(ev.type==="batch_relevance_start")card("batch_relevance","\u6279\u91cf\u76f8\u5173\u6027\u5f00\u59cb",`${ev.batch_count||0} batches`,ev,true);if(ev.type==="batch_relevance_request")card("batch_relevance",`Batch ${ev.batch_index}/${ev.batch_count}`,(ev.items||[]).map(x=>x.title).slice(0,2).join(" / "),ev);if(ev.type==="llm_request_start")llm(ev,true);if(ev.type==="llm_cache_hit")llm(ev,false,"cached");if(ev.type==="llm_request_done")finish(ev);if(ev.type==="llm_stream_delta")stream(ev);if(ev.type==="membership_candidates")card("event_membership",`#${ev.index} \u5019\u9009\u4e8b\u4ef6`,ev.news?.title||"",ev);if(ev.type==="membership_decision")card("event_membership",`#${ev.index} ${ev.decision||"decision"}`,ev.event_id||ev.reason||"",ev);if(ev.type==="merge_round_start")step("event_merge","running");if(ev.type==="merge_candidates")card("event_merge",`${ev.round||""} \u8f6e\u5408\u5e76\u5019\u9009`,ev.seed_event?.event_label||ev.seed_event?.event_id||"",ev);if(ev.type==="merge_decision")card("event_merge",`${ev.round||""} \u8f6e\u5408\u5e76\u51b3\u7b56`,(ev.merge_event_ids||[]).join(", ")||"no merge",ev);renderStats();renderTop()}
function norm(s){return ingestSources.has(s)?"ingest":(steps.some(x=>x[0]===s)?s:"pipeline")}function run(s,t){runDot.className=`dot ${s}`;runText.textContent=t}function cur(t){currentText.textContent=t}function timer(){if(state.timer)clearInterval(state.timer);state.timer=setInterval(renderTop,1000)}function renderTop(){eventCount.textContent=state.eventCount;llmCount.textContent=state.llmCount;errorCount.textContent=state.errorCount;let sec=state.startMs?Math.floor((Date.now()-state.startMs)/1000):0;elapsed.textContent=`${String(Math.floor(sec/60)).padStart(2,"0")}:${String(sec%60).padStart(2,"0")}`}function step(s,status){s=norm(s);for(const el of [document.getElementById(`step-${s}`),document.getElementById(`phase-${s}`)]){el?.classList.remove("running","done","error");if(status!=="idle")el?.classList.add(status)}let b=document.getElementById(`badge-${s}`),p=document.getElementById(`phase-status-${s}`);if(b){b.textContent=status;b.className=`badge ${status}`}if(p)p.textContent=status}function clearEmpty(s){document.querySelector(`#cards-${norm(s)} .empty`)?.remove()}function card(s,title,sub,payload,open=false){s=norm(s);clearEmpty(s);let id=`${payload.type||title}-${payload.id||payload.request_id||Math.random()}`;if(state.cards.has(id))return state.cards.get(id);let d=document.createElement("details");d.className="card";d.open=open;d.innerHTML=`<summary><div class="cardTop"><div><div class="title">${esc(title)}</div><div class="sub">${esc(sub||"")}</div></div><span class="badge status">${esc(payload.type||"event")}</span></div></summary><div class="body"><div class="label">Payload</div><pre class="payload"></pre><div class="label">Stream</div><pre class="stream"></pre><div class="label">Response</div><pre class="response"></pre></div>`;d.querySelector(".payload").textContent=JSON.stringify(payload,null,2);document.getElementById(`cards-${s}`).prepend(d);state.cards.set(id,d);return d}function llm(ev,open,status="running"){let s=ev.task==="batch_ai_relevance"?"batch_relevance":ev.task==="event_membership"?"event_membership":ev.task==="event_merge_group"?"event_merge":"pipeline";let c=card(s,ev.name||ev.task,ev.summary||ev.goal||"",ev,open);c.querySelector(".status").textContent=status;cur(`LLM: ${ev.name||ev.task}`)}function finish(ev){let c=state.cards.get(ev.request_id);if(c){c.querySelector(".status").textContent="done";c.querySelector(".response").textContent=JSON.stringify(ev.response||{},null,2)}}function stream(ev){let c=state.cards.get(ev.request_id);if(c)c.querySelector(".stream").textContent+=ev.delta||""}function renderStats(){let rows=[[T.total,state.stats.total??state.stats.item_count],[T.classified,state.stats.classified],[T.events,state.stats.events??state.stats.event_count],[T.discarded,state.stats.discarded_count],[T.progress,state.stats.total_candidates?`${state.stats.processed_candidates||0}/${state.stats.total_candidates}`:""],[T.merged,state.stats.merged_event_count]];stats.innerHTML=rows.map(([k,v])=>`<div class="stat"><span>${esc(k)}</span><b>${v??""}</b></div>`).join("")}function esc(x){return String(x||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[c]))}function reset(){state.cards.clear();state.stats={};state.recent=[];state.eventCount=0;state.llmCount=0;state.errorCount=0;state.startMs=Date.now();steps.forEach(([s])=>{document.getElementById(`cards-${s}`).innerHTML='<div class="empty">Waiting for events</div>';step(s,"idle")});recent.textContent="";run("running","\u542f\u52a8\u4e2d");cur("\u5df2\u63d0\u4ea4\u8fd0\u884c\u8bf7\u6c42...");timer();renderTop();renderStats()}function start(payload){reset();payload.config=configPath.value||"config.local.json";fetch("/api/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}).then(r=>r.json()).then(p=>{if(!p.ok){run("error","\u542f\u52a8\u5931\u8d25");cur(p.error||"start failed")}})}runBtn.onclick=()=>start({reset_classification:true});resumeBtn.onclick=()=>start({reset_classification:false});init();
</script></body></html>
"""

if __name__ == "__main__":
    main()
