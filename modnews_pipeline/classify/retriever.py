from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import requests

from modnews_pipeline.config import EmbeddingConfig
from modnews_pipeline.models import EventRecord, NewsItem
from modnews_pipeline.progress import emit, new_request_id, simulate_cached_latency

_VECTOR_CACHE_LOCK = threading.Lock()


@dataclass(slots=True)
class EventVectorRetriever:
    config: EmbeddingConfig
    session: requests.Session
    _memory_cache: dict[str, list[float]] = field(default_factory=dict)
    _memory_lock: threading.Lock = field(default_factory=threading.Lock)

    def embed_text_for_clustering(self, text: str) -> list[float]:
        return self._embed_text(text)

    def search(
        self,
        *,
        item: NewsItem,
        item_pubtime: datetime | None,
        events: list[EventRecord],
        limit: int,
        time_window_hours: int,
    ) -> list[EventRecord]:
        if not events:
            return []
        query_vector = self._embed_text(_news_text(item))
        scored: list[tuple[float, EventRecord]] = []
        for event in events:
            if _outside_time_window(item_pubtime, _parse_datetime(event.latest_pubtime), time_window_hours):
                continue
            event_vector = self._embed_text(_event_text(event))
            similarity = cosine_similarity(query_vector, event_vector)
            scored.append((similarity, event))
        scored.sort(key=lambda row: row[0], reverse=True)
        return [event for _, event in scored[:limit]]

    def search_for_event(
        self,
        *,
        seed: EventRecord,
        events: list[EventRecord],
        limit: int,
        time_window_hours: int,
    ) -> list[EventRecord]:
        if not events:
            return []
        query_vector = self._embed_text(_event_text(seed))
        seed_pubtime = _parse_datetime(seed.latest_pubtime)
        scored: list[tuple[float, EventRecord]] = []
        for event in events:
            if event.event_id == seed.event_id:
                continue
            if _outside_time_window(seed_pubtime, _parse_datetime(event.latest_pubtime), time_window_hours):
                continue
            event_vector = self._embed_text(_event_text(event))
            similarity = cosine_similarity(query_vector, event_vector)
            scored.append((similarity, event))
        scored.sort(key=lambda row: row[0], reverse=True)
        return [event for _, event in scored[:limit]]

    def _embed_text(self, text: str) -> list[float]:
        memory_key = self._cache_key(text)
        with self._memory_lock:
            memory_cached = self._memory_cache.get(memory_key)
        if memory_cached is not None:
            return memory_cached

        request_id = new_request_id("embedding")
        cached = self._read_cache(text)
        if cached is not None:
            with self._memory_lock:
                self._memory_cache[memory_key] = cached
            emit(
                "embedding_cache_hit",
                request_id=request_id,
                model=self.config.model,
                text_preview=text[:240],
                vector_dimensions=len(cached),
                simulated=self.config.simulate_cache_stream,
            )
            if self.config.simulate_cache_stream:
                simulate_cached_latency(
                    first_token_delay_seconds=self.config.cache_first_token_delay_seconds,
                    tokens_per_second=self.config.cache_tokens_per_second,
                    text=text,
                )
                emit(
                    "embedding_request_done",
                    request_id=request_id,
                    model=self.config.model,
                    cached=True,
                    simulated=True,
                    vector_dimensions=len(cached),
                )
            return cached
        if not self.config.base_url:
            raise ValueError("EMBEDDING_BASE_URL is required for vector event retrieval")
        if not self.config.api_key:
            raise ValueError("EMBEDDING_API_KEY is required for vector event retrieval")

        emit("embedding_request_start", request_id=request_id, model=self.config.model, text_preview=text[:240])
        response = self.session.post(
            f"{self.config.base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {self.config.api_key}"},
            json={"model": self.config.model, "input": text},
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        vector = payload["data"][0]["embedding"]
        with self._memory_lock:
            self._memory_cache[memory_key] = vector
        self._write_cache(text, vector)
        emit(
            "embedding_request_done",
            request_id=request_id,
            model=self.config.model,
            cached=False,
            vector_dimensions=len(vector),
        )
        return vector

    def _cache_key(self, text: str) -> str:
        payload = {"model": self.config.model, "text": text}
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _read_cache(self, text: str) -> list[float] | None:
        if not self.config.cache_path:
            return None
        key = self._cache_key(text)
        with _VECTOR_CACHE_LOCK:
            self._ensure_cache()
            with sqlite3.connect(self.config.cache_path) as conn:
                row = conn.execute("SELECT vector_json FROM vector_cache WHERE cache_key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def _write_cache(self, text: str, vector: list[float]) -> None:
        if not self.config.cache_path:
            return
        key = self._cache_key(text)
        with _VECTOR_CACHE_LOCK:
            self._ensure_cache()
            with sqlite3.connect(self.config.cache_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO vector_cache (cache_key, model, text_hash, vector_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        key,
                        self.config.model,
                        hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        json.dumps(vector, ensure_ascii=False),
                    ),
                )

    def _ensure_cache(self) -> None:
        assert self.config.cache_path is not None
        Path(self.config.cache_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.config.cache_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vector_cache (
                    cache_key TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    text_hash TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _news_text(item: NewsItem) -> str:
    return "\n".join(
        part
        for part in [
            item.canonical_summary,
            item.title,
            " ".join(item.entities),
            item.event_type,
        ]
        if part
    )


def _event_text(event: EventRecord) -> str:
    return "\n".join(
        part
        for part in [
            event.event_label,
            event.event_summary,
            " ".join(event.key_entities),
            event.event_type,
            "\n".join(event.representative_titles),
        ]
        if part
    )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _outside_time_window(left: datetime | None, right: datetime | None, hours: int) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) > timedelta(hours=hours)
