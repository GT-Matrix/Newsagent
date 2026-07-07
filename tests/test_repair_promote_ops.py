from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.repository.source_config import source_config_store
from modnews.service.extraction.metadata import ExtractorMetadata, metadata_comment, read_metadata
from modnews.service.extraction.registry import ExtractorRegistry
from modnews.service.extraction.repair_promote_ops import (
    apply_promoted_metadata,
    infer_target_url,
    sync_source_config_for_record,
    write_promoted_manifest,
)


class RepairPromoteOpsTest(unittest.TestCase):
    def _registry_with_record(self, project_root: Path):
        current_dir = project_root / "extractors" / "site-1" / "current"
        current_dir.mkdir(parents=True, exist_ok=True)
        metadata = ExtractorMetadata(
            id="site-1",
            name="site-1",
            kind="news",
            version="1.0.0",
            status="disabled",
        )
        (current_dir / "extractor.py").write_text(
            f"{metadata_comment(metadata)}\nDEFAULT_URL = 'https://example.com'\n",
            encoding="utf-8",
        )
        (current_dir / "manifest.json").write_text(json.dumps({"id": "site-1", "status": "disabled"}), encoding="utf-8")
        return ExtractorRegistry(project_root / "extractors").get("site-1")

    def test_apply_promoted_metadata_updates_comment_and_infers_name_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            record = self._registry_with_record(project_root)
            task_md = project_root / "TASK.md"
            task_md.write_text("Create extractor for Example Site: https://example.com\n", encoding="utf-8")

            updated = apply_promoted_metadata(
                record,
                result={"version": "2.0.0"},
                extractor_path=record.extractor_path,
                task_md_path=task_md,
            )

            self.assertEqual(updated.metadata.version, "2.0.0")
            self.assertEqual(updated.metadata.status, "enabled")
            self.assertEqual(updated.metadata.target_url, "https://example.com")
            self.assertEqual(updated.metadata.name, "Example Site")
            reloaded = read_metadata(record.extractor_path)
            self.assertEqual(reloaded.version, "2.0.0")
            self.assertEqual(reloaded.name, "Example Site")

    def test_write_promoted_manifest_carries_promoted_task_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            record = self._registry_with_record(project_root)

            manifest = write_promoted_manifest(
                record,
                source_manifest_path=record.manifest_path,
                task_id="repair-1",
            )

            self.assertEqual(manifest["promoted_from_task"], "repair-1")
            written = json.loads(record.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(written["promoted_from_task"], "repair-1")
            self.assertEqual(written["status"], "enabled")

    def test_sync_source_config_for_record_updates_site_list_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            record = self._registry_with_record(project_root)
            record.metadata.name = "Example Site"
            record.metadata.status = "enabled"
            record.metadata.target_url = "https://example.com"
            record.metadata.tags = ["ai", "news"]

            sync_source_config_for_record(project_root, record)

            config = source_config_store(project_root).load()
            site = config["sources"]["site_lists"]["site-1"]
            self.assertTrue(site["enabled"])
            self.assertEqual(site["name"], "Example Site")
            self.assertEqual(site["url"], "https://example.com")
            self.assertEqual(site["extractor_id"], "site-1")
            self.assertEqual(site["tags"], ["ai", "news"])

    def test_infer_target_url_reads_default_url_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extractor.py"
            path.write_text("DEFAULT_URL = 'https://example.com/a'\n", encoding="utf-8")
            self.assertEqual(infer_target_url(path), "https://example.com/a")


if __name__ == "__main__":
    unittest.main()
