from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

_VECTOR_CACHE_LOCK = threading.Lock()


class VectorCacheRepository:
    def __init__(self, path: Path | None) -> None:
        self.path = path

    def get(self, cache_key: str) -> list[float] | None:
        if not self.path:
            return None
        with _VECTOR_CACHE_LOCK:
            self._ensure_schema()
            with sqlite3.connect(self.path) as conn:
                row = conn.execute("SELECT vector_json FROM vector_cache WHERE cache_key = ?", (cache_key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, cache_key: str, *, model: str, text_hash: str, vector: list[float]) -> None:
        if not self.path:
            return
        with _VECTOR_CACHE_LOCK:
            self._ensure_schema()
            with sqlite3.connect(self.path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO vector_cache (cache_key, model, text_hash, vector_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        cache_key,
                        model,
                        text_hash,
                        json.dumps(vector, ensure_ascii=False),
                    ),
                )

    def _ensure_schema(self) -> None:
        assert self.path is not None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
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
