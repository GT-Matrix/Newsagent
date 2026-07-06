from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime

import requests

from modnews.core.config import EmbeddingConfig
from modnews.core.models import EventRecord, NewsItem
from modnews.core.progress import emit, new_request_id, simulate_cached_latency
from modnews.repository.vector_cache import VectorCacheRepository
from .retriever_ops import cosine_similarity, event_text, news_text, parse_datetime, rank_event_candidates


@dataclass(slots=True)
class EventVectorRetriever:
    config: EmbeddingConfig
    session: requests.Session
    _memory_cache: dict[str, list[float]] = field(default_factory=dict)
    _memory_lock: threading.Lock = field(default_factory=threading.Lock)
    _cache_repo: VectorCacheRepository | None = field(default=None, init=False, repr=False)

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
        return rank_event_candidates(
            query_vector=self._embed_text(news_text(item)),
            query_pubtime=item_pubtime,
            events=events,
            limit=limit,
            time_window_hours=time_window_hours,
            vector_for_event=lambda event: self._embed_text(event_text(event)),
        )

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
        return rank_event_candidates(
            query_vector=self._embed_text(event_text(seed)),
            query_pubtime=parse_datetime(seed.latest_pubtime),
            events=events,
            limit=limit,
            time_window_hours=time_window_hours,
            vector_for_event=lambda event: self._embed_text(event_text(event)),
            exclude_event_id=seed.event_id,
        )

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
        self._write_cache(memory_key, text, vector)
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
        return self._cache_repository().get(self._cache_key(text))

    def _write_cache(self, cache_key: str, text: str, vector: list[float]) -> None:
        self._cache_repository().put(
            cache_key,
            model=self.config.model,
            text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            vector=vector,
        )

    def _cache_repository(self) -> VectorCacheRepository:
        if self._cache_repo is None:
            self._cache_repo = VectorCacheRepository(self.config.cache_path)
        return self._cache_repo
