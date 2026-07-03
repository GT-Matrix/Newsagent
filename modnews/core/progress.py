from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from modnews.core.events import EventRouter


@dataclass(slots=True)
class ProgressEvent:
    id: int
    type: str
    ts: float
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "ts": self.ts, **self.data}


@dataclass(slots=True)
class ProgressBus:
    max_events: int = 5000
    _events: deque[ProgressEvent] = field(default_factory=deque)
    _listeners: list[queue.Queue[ProgressEvent]] = field(default_factory=list)
    _routers: list[EventRouter] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _next_id: int = 1
    _stats: dict[str, Any] = field(default_factory=dict)

    def emit(self, event_type: str, **data: Any) -> ProgressEvent:
        with self._lock:
            event = ProgressEvent(self._next_id, event_type, time.time(), data)
            self._next_id += 1
            self._events.append(event)
            while len(self._events) > self.max_events:
                self._events.popleft()
            if event_type in {"pipeline_start", "pipeline_done", "pipeline_error", "checkpoint", "step_start", "step_done"}:
                self._stats.update(_stats_from_event(event_type, data))
            listeners = list(self._listeners)
        _print_event(event)
        for listener in listeners:
            try:
                listener.put_nowait(event)
            except queue.Full:
                pass
        self._dispatch(event)
        return event

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "events": [event.to_dict() for event in self._events],
                "stats": dict(self._stats),
            }

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._stats.clear()
            self._next_id = 1

    def listen(self) -> queue.Queue[ProgressEvent]:
        listener: queue.Queue[ProgressEvent] = queue.Queue(maxsize=1000)
        with self._lock:
            self._listeners.append(listener)
        return listener

    def unlisten(self, listener: queue.Queue[ProgressEvent]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def bind_router(self, router: EventRouter) -> None:
        with self._lock:
            if router not in self._routers:
                self._routers.append(router)

    def unbind_router(self, router: EventRouter) -> None:
        with self._lock:
            if router in self._routers:
                self._routers.remove(router)

    def _dispatch(self, event: ProgressEvent) -> None:
        with self._lock:
            routers = list(self._routers)
        payload = {"event": event.to_dict()}
        for router in routers:
            router.dispatch("progress", payload)
            router.dispatch(f"progress.{event.type}", payload)


BUS = ProgressBus()


def emit(event_type: str, **data: Any) -> ProgressEvent:
    return BUS.emit(event_type, **data)


def new_request_id(task: str) -> str:
    return f"{task}-{uuid.uuid4().hex[:10]}"


def sse(event: ProgressEvent) -> str:
    payload = json.dumps(event.to_dict(), ensure_ascii=False)
    return f"id: {event.id}\nevent: {event.type}\ndata: {payload}\n\n"


def compact_messages(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [{"role": row.get("role"), "content": row.get("content", "")} for row in messages]


def simulate_stream(
    *,
    request_id: str,
    text: str,
    first_token_delay_seconds: float,
    tokens_per_second: float,
    chunk_event: str = "llm_stream_delta",
    chunk_key: str = "delta",
) -> None:
    if first_token_delay_seconds > 0:
        time.sleep(first_token_delay_seconds)
    rate = max(tokens_per_second, 1.0)
    chunk_size = max(1, int(rate / 10))
    delay = chunk_size / rate
    for start in range(0, len(text), chunk_size):
        chunk = text[start : start + chunk_size]
        emit(chunk_event, request_id=request_id, simulated=True, **{chunk_key: chunk})
        if start + chunk_size < len(text):
            time.sleep(delay)


def estimated_token_count(text: str) -> int:
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = max(len(text) - ascii_chars, 0)
    return max(1, int(ascii_chars / 4 + non_ascii_chars / 1.7))


def simulate_cached_latency(
    *,
    first_token_delay_seconds: float,
    tokens_per_second: float,
    text: str,
) -> None:
    if first_token_delay_seconds > 0:
        time.sleep(first_token_delay_seconds)
    token_count = estimated_token_count(text)
    time.sleep(token_count / max(tokens_per_second, 1.0))


def describe_llm_request(task: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    user_payload = _last_user_json(messages)
    if task == "batch_ai_relevance":
        items = user_payload.get("items", []) if isinstance(user_payload, dict) else []
        titles = [_news_brief(row) for row in items[:5]]
        return {
            "name": "\u6279\u91cf AI \u76f8\u5173\u6027\u5224\u65ad",
            "goal": f"\u5224\u65ad {len(items)} \u6761\u6807\u9898\u662f\u5426\u662f AI \u6838\u5fc3\u65b0\u95fb\uff0c\u8f93\u51fa candidate / suspect / discard\u3002",
            "summary": "\uff1b".join(titles),
            "payload": user_payload,
        }
    if task == "clustered_event_extraction":
        items = user_payload.get("items", []) if isinstance(user_payload, dict) else []
        titles = [_news_brief(row) for row in items[:5]]
        return {
            "name": "标题聚类抽取",
            "goal": f"从 {len(items)} 条聚类标题中抽取 AI 事件、疑似项和丢弃原因。",
            "summary": "；".join(titles),
            "payload": user_payload,
        }
    if task == "clustered_event_merge":
        events = user_payload.get("events", []) if isinstance(user_payload, dict) else []
        labels = [_event_brief(row) for row in events[:5]]
        return {
            "name": "事件聚类合并",
            "goal": f"判断 {len(events)} 个聚类事件中哪些描述同一具体 AI 事件。",
            "summary": "；".join(labels),
            "payload": user_payload,
        }
    if task == "event_membership":
        news = user_payload.get("news", {}) if isinstance(user_payload, dict) else {}
        candidates = user_payload.get("candidate_events", []) if isinstance(user_payload, dict) else []
        return {
            "name": "\u4e8b\u4ef6\u5f52\u5e76",
            "goal": f"\u628a\u65b0\u95fb\u5f52\u5165 {len(candidates)} \u4e2a\u5019\u9009\u4e8b\u4ef6\u4e4b\u4e00\uff0c\u6216\u521b\u5efa/\u4e22\u5f03\u3002",
            "summary": _news_brief(news),
            "payload": user_payload,
        }
    if task == "event_merge_group":
        seed = user_payload.get("seed_event", {}) if isinstance(user_payload, dict) else {}
        candidates = user_payload.get("candidate_events", []) if isinstance(user_payload, dict) else []
        return {
            "name": "\u4e8b\u4ef6\u4e8c\u6b21\u5408\u5e76",
            "goal": f"\u4ee5 seed \u4e8b\u4ef6\u4e3a\u4e2d\u5fc3\uff0c\u5728 {len(candidates)} \u4e2a\u5411\u91cf\u5019\u9009\u91cc\u5224\u65ad\u54ea\u4e9b\u5e94\u8be5\u5408\u5e76\u3002",
            "summary": _event_brief(seed),
            "payload": user_payload,
        }
    if task == "suspect_article_review":
        title = user_payload.get("title", "") if isinstance(user_payload, dict) else ""
        return {
            "name": "\u7591\u4f3c\u65b0\u95fb\u6b63\u6587\u590d\u6838",
            "goal": "\u6839\u636e\u6b63\u6587\u6458\u5f55\u5224\u65ad\u7591\u4f3c\u6807\u9898\u662f\u5426\u5e94\u8fdb\u5165\u4e8b\u4ef6\u5f52\u7c7b\u3002",
            "summary": title,
            "payload": user_payload,
        }
    return {"name": task, "goal": "\u8bf7\u6c42 LLM \u8fd4\u56de\u7ed3\u6784\u5316 JSON\u3002", "summary": task, "payload": user_payload}




def _print_event(event: ProgressEvent) -> None:
    message = _event_message(event.type, event.data)
    if not message:
        return
    ts = datetime.fromtimestamp(event.ts).strftime("%H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def _event_message(event_type: str, data: dict[str, Any]) -> str | None:
    if event_type == "pipeline_start":
        return f"pipeline start config={data.get('config_path', '')}"
    if event_type == "pipeline_done":
        stats = data.get("stats", {}) or {}
        return f"pipeline done total={stats.get('total', '')} events={stats.get('events', '')} output={data.get('output_path', '')}"
    if event_type == "pipeline_error":
        return f"pipeline error {data.get('error', '')}"
    if event_type == "step_start":
        return f"step start {data.get('step', '')} stage={data.get('stage', '')}"
    if event_type == "step_done":
        extra = []
        if data.get("item_count") is not None:
            extra.append(f"items={data.get('item_count')}")
        if data.get("event_count") is not None:
            extra.append(f"events={data.get('event_count')}")
        return f"step done {data.get('step', '')} {' '.join(extra)}".strip()
    if event_type == "step_skip":
        return f"step skip {data.get('step', '')} stage={data.get('stage', '')}"
    if event_type == "ingest_source_start":
        return f"ingest start source={data.get('source', '')}"
    if event_type == "ingest_source_done":
        errors = data.get("errors") or []
        suffix = f" errors={len(errors)}" if errors else ""
        return f"ingest done source={data.get('source', '')} items={data.get('item_count', '')}{suffix}"
    if event_type == "batch_relevance_start":
        return f"relevance start batches={data.get('batch_count', '')} batch_size={data.get('batch_size', '')} concurrency={data.get('concurrency', '')}"
    if event_type == "batch_relevance_request":
        return f"relevance batch request {data.get('batch_index', '')}/{data.get('batch_count', '')} size={len(data.get('items') or [])}"
    if event_type == "batch_relevance_done":
        return f"relevance batch done {data.get('batch_index', '')}/{data.get('batch_count', '')}"
    if event_type == "llm_request_start":
        return f"llm request task={data.get('task', '')} model={data.get('model', '')}"
    if event_type == "llm_cache_hit":
        return f"llm cache hit task={data.get('task', '')}"
    if event_type == "llm_request_retry":
        return f"llm retry task={data.get('task', '')} attempt={data.get('attempt', '')}/{data.get('max_retries', '')} error={data.get('error', '')}"
    if event_type == "llm_request_error":
        return f"llm error task={data.get('task', '')} error={data.get('error', '')}"
    if event_type == "llm_request_done":
        return f"llm done task={data.get('task', '')} status={data.get('status', '')}"
    if event_type == "embedding_request_start":
        return f"embedding request model={data.get('model', '')}"
    if event_type == "embedding_cache_hit":
        return "embedding cache hit"
    if event_type == "embedding_request_done":
        return f"embedding done cached={data.get('cached', False)}"
    if event_type == "membership_candidates":
        return f"membership candidates index={data.get('index', '')} count={len(data.get('candidate_events') or [])}"
    if event_type == "membership_decision":
        return f"membership decision index={data.get('index', '')} decision={data.get('decision', '')} event={data.get('event_id', '')}"
    if event_type == "merge_round_start":
        return f"merge round start round={data.get('round', '')} events={data.get('event_count', '')}"
    if event_type == "merge_round_done":
        return f"merge round done round={data.get('round', '')} groups={data.get('merged_group_count', '')} events={data.get('event_count', '')}"
    if event_type == "merge_candidates":
        return f"merge candidates round={data.get('round', '')} count={len(data.get('candidate_events') or [])}"
    if event_type == "merge_decision":
        return f"merge decision round={data.get('round', '')} seed={data.get('seed_event_id', '')} merge_count={len(data.get('merge_event_ids') or [])}"
    if event_type == "checkpoint":
        meta = data.get("meta", {}) or {}
        return f"checkpoint stage={meta.get('stage', '')} processed={meta.get('processed_candidates', '')}/{meta.get('total_candidates', '')} path={data.get('path', '')}"
    return None
def _last_user_json(messages: list[dict[str, str]]) -> Any:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        try:
            return json.loads(message.get("content") or "{}")
        except json.JSONDecodeError:
            return {"text": message.get("content", "")}
    return {}


def _news_brief(row: dict[str, Any]) -> str:
    index = row.get("index")
    title = row.get("title") or row.get("canonical_summary") or ""
    prefix = f"#{index} " if index is not None else ""
    return f"{prefix}{title}"[:160]


def _event_brief(row: dict[str, Any]) -> str:
    event_id = row.get("event_id", "")
    label = row.get("event_label") or row.get("event_summary") or ""
    return f"{event_id} {label}".strip()[:160]


def _stats_from_event(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    if event_type == "pipeline_start":
        return {"status": "running", "started_at": data.get("started_at")}
    if event_type == "pipeline_done":
        return {"status": "done", "finished_at": data.get("finished_at"), **data.get("stats", {})}
    if event_type == "pipeline_error":
        return {"status": "error", "error": data.get("error")}
    if event_type == "checkpoint":
        return data.get("meta", {})
    if event_type == "step_start":
        return {"current_step": data.get("step")}
    if event_type == "step_done":
        return {"last_step": data.get("step")}
    return {}
