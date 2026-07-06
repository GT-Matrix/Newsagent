from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from modnews.core.config import build_config
from modnews.repository.runtime_config_store import runtime_config_store


class RuntimeEnvLoadingTest(unittest.TestCase):
    def test_build_config_loads_root_env_runtime_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / ".env.runtime").write_text(
                "\n".join(
                    [
                        "LLM_BASE_URL=https://example-llm.test/v1",
                        "LLM_API_KEY=test-llm-key",
                        "EMBEDDING_BASE_URL=https://example-embedding.test/v1",
                        "EMBEDDING_API_KEY=test-embedding-key",
                    ]
                ),
                encoding="utf-8",
            )
            old_values = {key: os.environ.pop(key, None) for key in ("LLM_BASE_URL", "LLM_API_KEY", "EMBEDDING_BASE_URL", "EMBEDDING_API_KEY")}
            try:
                config = build_config(base_dir=project_root)
            finally:
                for key, value in old_values.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

            self.assertEqual(config.classification.llm.base_url, "https://example-llm.test/v1")
            self.assertEqual(config.classification.llm.api_key, "test-llm-key")
            self.assertEqual(config.classification.embedding.base_url, "https://example-embedding.test/v1")
            self.assertEqual(config.classification.embedding.api_key, "test-embedding-key")

    def test_build_config_and_runtime_store_drop_legacy_suspect_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            store = runtime_config_store(project_root)
            payload = store.load()
            payload.setdefault("classification", {})["suspect_mode"] = "article"
            store.save(payload)

            normalized = store.load()
            config = build_config(base_dir=project_root)

            self.assertNotIn("suspect_mode", normalized["classification"])
            self.assertFalse(hasattr(config.classification, "suspect_mode"))


if __name__ == "__main__":
    unittest.main()
