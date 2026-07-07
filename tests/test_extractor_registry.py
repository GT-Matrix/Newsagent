from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.cli.local_client import LocalClient
from modnews.service.extraction.contract import ExtractorRunInput
from modnews.service.extraction.metadata import ExtractorMetadata, metadata_comment
from modnews.service.extraction.query_facade import ExtractionQueryFacade
from modnews.service.extraction.repair_runtime_facade import RepairRuntimeFacade
from modnews.service.extraction.registry import ExtractorRegistry


class ExtractorRegistryTest(unittest.TestCase):
    def test_query_facade_lists_and_shows_extractor_related_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            self._write_extractor(project_root, "extractor-1", status="enabled")
            client = LocalClient(project_root)
            client.sources_site_add("site-1", "https://example.com", extractor_id="extractor-1")
            client.repair_create({"source_id": "extractor-1", "reason": "test repair", "auto_start": False})
            facade = ExtractionQueryFacade(
                project_root=project_root,
                repair_runtime=RepairRuntimeFacade(
                    project_root=project_root,
                    queue=client.container.event_queue,
                    queue_show=client.queue_show,
                ),
            )

            rows = facade.list_extractors()
            detail = facade.show_extractor("extractor-1", config=client.config_show())

            self.assertEqual([row["metadata"]["id"] for row in rows], ["extractor-1"])
            self.assertEqual(detail["record"]["metadata"]["id"], "extractor-1")
            self.assertEqual(detail["bound_sources"][0]["id"], "site-1")
            self.assertEqual(detail["repair_tasks"][0]["source_id"], "extractor-1")

    def test_get_and_list_read_scanned_extractor_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            self._write_extractor(project_root, "site-1", status="enabled")

            registry = ExtractorRegistry(project_root / "extractors")
            record = registry.get("site-1")

            self.assertEqual(record.metadata.id, "site-1")
            self.assertEqual(record.manifest["id"], "site-1")
            self.assertEqual([item.metadata.id for item in registry.list()], ["site-1"])

    def test_set_enabled_updates_metadata_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            extractor_path = self._write_extractor(project_root, "site-1", status="disabled")
            registry = ExtractorRegistry(project_root / "extractors")

            updated = registry.set_enabled("site-1", True)

            self.assertEqual(updated.metadata.status, "enabled")
            self.assertEqual(updated.manifest["status"], "enabled")
            reloaded_text = extractor_path.read_text(encoding="utf-8")
            self.assertIn('"status": "enabled"', reloaded_text)

    def test_run_executes_enabled_extractor_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            self._write_extractor(project_root, "site-1", status="enabled")
            registry = ExtractorRegistry(project_root / "extractors")

            result = registry.run(
                "site-1",
                ExtractorRunInput(
                    source_id="site-1",
                    url="https://example.com",
                    scrape_date="2026-07-06T00:00:00+08:00",
                    limit=3,
                ),
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.items[0].platform, "site-1")
            self.assertEqual(result.extractor_version, "1.0.0")

    def test_run_rejects_disabled_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            self._write_extractor(project_root, "site-1", status="disabled")
            registry = ExtractorRegistry(project_root / "extractors")

            with self.assertRaisesRegex(RuntimeError, "extractor site-1 is disabled"):
                registry.run(
                    "site-1",
                    ExtractorRunInput(
                        source_id="site-1",
                        url="https://example.com",
                        scrape_date="2026-07-06T00:00:00+08:00",
                    ),
                )

    def _write_extractor(self, project_root: Path, source_id: str, *, status: str) -> Path:
        current_dir = project_root / "extractors" / source_id / "current"
        current_dir.mkdir(parents=True, exist_ok=True)
        metadata = ExtractorMetadata(
            id=source_id,
            name=source_id,
            kind="news",
            version="1.0.0",
            status=status,
        )
        extractor_path = current_dir / "extractor.py"
        extractor_path.write_text(
            (
                f"{metadata_comment(metadata)}\n"
                "from __future__ import annotations\n\n"
                "def run(payload: dict) -> dict:\n"
                "    return {\n"
                '        "ok": True,\n'
                '        "items": [{\n'
                '            "platform": payload.get("source_id"),\n'
                '            "title": "Example",\n'
                '            "url": payload.get("url"),\n'
                '            "pubtime": None,\n'
                '            "scrape_date": payload.get("scrape_date"),\n'
                "        }],\n"
                '        "diagnostics": {"limit": payload.get("limit")},\n'
                '        "extractor_version": "1.0.0",\n'
                "    }\n"
            ),
            encoding="utf-8",
        )
        (current_dir / "manifest.json").write_text(
            json.dumps({"id": source_id, "status": status}, ensure_ascii=False),
            encoding="utf-8",
        )
        return extractor_path


if __name__ == "__main__":
    unittest.main()
