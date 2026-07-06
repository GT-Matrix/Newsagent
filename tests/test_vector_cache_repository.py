from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.repository.vector_cache import VectorCacheRepository


class VectorCacheRepositoryTest(unittest.TestCase):
    def test_put_and_get_roundtrip_vector_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache" / "vectors.sqlite3"
            repo = VectorCacheRepository(path)

            repo.put(
                "cache-key-1",
                model="embedding-model",
                text_hash="hash-1",
                vector=[0.1, 0.2, 0.3],
            )

            self.assertEqual(repo.get("cache-key-1"), [0.1, 0.2, 0.3])

    def test_get_returns_none_when_cache_path_missing_or_key_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache" / "vectors.sqlite3"
            self.assertIsNone(VectorCacheRepository(None).get("missing"))
            self.assertIsNone(VectorCacheRepository(path).get("missing"))


if __name__ == "__main__":
    unittest.main()
