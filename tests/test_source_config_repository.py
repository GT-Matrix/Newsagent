from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.cli.local_client import LocalClient
from modnews.repository.source_config import SourceConfigRepository


class SourceConfigRepositoryTest(unittest.TestCase):
    def test_sources_facade_lists_and_updates_rss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = SourceConfigRepository(Path(tmp))

            repo.upsert_rss("example", {"url": "https://example.com/feed", "name": "Example", "enabled": True})
            rows = repo.list("rss")
            self.assertEqual(rows[0]["id"], "example")
            self.assertEqual(rows[0]["source_type"], "rss")

            repo.disable_rss("example")
            rows = repo.list("rss")
            self.assertFalse(rows[0]["enabled"])

    def test_sources_facade_adds_site_and_updates_step_sites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = SourceConfigRepository(Path(tmp))

            repo.upsert_site(
                "site-1",
                {
                    "url": "https://example.com",
                    "name": "Site",
                    "extractor_id": "extractor-1",
                    "enabled": True,
                },
            )
            config = repo.load()

            self.assertIn("site-1", config["sources"]["site_lists"])
            self.assertIn("site-1", config["steps"]["site_lists"]["sites"])

    def test_local_client_sources_commands_use_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            client.sources_rss_add("example", "https://example.com/feed", name="Example")
            client.sources_site_add("site-1", "https://example.com", extractor_id="extractor-1")

            self.assertEqual({row["id"] for row in client.sources_list("rss")}, {"example"})
            self.assertEqual({row["id"] for row in client.sources_list("site_lists")}, {"site-1"})


if __name__ == "__main__":
    unittest.main()
