from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.core.config import LlmConfig
from modnews.repository.llm_cache import LlmCacheRepository


class LlmCacheRepositoryTest(unittest.TestCase):
    def test_write_and_read_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = LlmConfig(
                model="test-model",
                base_url="https://example.com/v1",
                api_key="key",
                cache_path=Path(tmp) / "cache" / "llm.sqlite3",
            )
            repo = LlmCacheRepository(config)
            messages = [{"role": "user", "content": "hello"}]

            repo.write("task-1", messages, {"ok": True, "value": 1})

            self.assertEqual(repo.read("task-1", messages), {"ok": True, "value": 1})

    def test_read_returns_none_when_cache_disabled_or_missing(self) -> None:
        messages = [{"role": "user", "content": "hello"}]
        disabled = LlmConfig(model="test-model", base_url="https://example.com/v1", api_key="key", cache_path=None)
        self.assertIsNone(LlmCacheRepository(disabled).read("task-1", messages))
        with tempfile.TemporaryDirectory() as tmp:
            config = LlmConfig(
                model="test-model",
                base_url="https://example.com/v1",
                api_key="key",
                cache_path=Path(tmp) / "cache" / "llm.sqlite3",
            )
            self.assertIsNone(LlmCacheRepository(config).read("task-1", messages))


if __name__ == "__main__":
    unittest.main()
