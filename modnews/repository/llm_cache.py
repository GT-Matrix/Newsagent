from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from modnews.core.config import LlmConfig

_CACHE_LOCK = threading.Lock()


class LlmCacheRepository:
    def __init__(self, config: LlmConfig) -> None:
        self.config = config

    def read(self, task: str, messages: list[dict[str, str]]) -> dict[str, Any] | None:
        if not self.config.cache_path:
            return None
        key = self.cache_key(task, messages)
        with _CACHE_LOCK:
            self._ensure_cache()
            with sqlite3.connect(self.config.cache_path) as conn:
                row = conn.execute("SELECT response_json FROM llm_cache WHERE cache_key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def write(self, task: str, messages: list[dict[str, str]], response: dict[str, Any]) -> None:
        if not self.config.cache_path:
            return
        key = self.cache_key(task, messages)
        with _CACHE_LOCK:
            self._ensure_cache()
            with sqlite3.connect(self.config.cache_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO llm_cache (cache_key, task, response_json)
                    VALUES (?, ?, ?)
                    """,
                    (key, task, json.dumps(response, ensure_ascii=False, sort_keys=True)),
                )

    def cache_key(self, task: str, messages: list[dict[str, str]]) -> str:
        payload = {
            "task": task,
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": messages,
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _ensure_cache(self) -> None:
        assert self.config.cache_path is not None
        Path(self.config.cache_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.config.cache_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_cache (
                    cache_key TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
