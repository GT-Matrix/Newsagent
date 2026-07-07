from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.service.extraction.metadata import ExtractorMetadata, metadata_comment
from modnews.service.extraction.registry import ExtractorRegistry
from modnews.service.extraction.repair_workspace import prepare_repair_workspace, publish_repair_workspace


class RepairWorkspaceTest(unittest.TestCase):
    def test_prepare_repair_workspace_bootstraps_missing_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            workspace = prepare_repair_workspace(
                tasks_root=project_root / "agent_work" / "extractors",
                registry=ExtractorRegistry(project_root / "extractors"),
                source_id="site-1",
                source_metadata={"url": "https://example.com", "name": "Example"},
                task_id="site-1-20260706",
            )

            self.assertTrue(workspace.bootstrap)
            self.assertEqual(workspace.task_id, "site-1-20260706")
            self.assertTrue((workspace.work_dir / "current" / "extractor.py").exists())
            manifest = json.loads((workspace.work_dir / "current" / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["bootstrap"])

    def test_prepare_repair_workspace_copies_existing_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            current_dir = project_root / "extractors" / "site-1" / "current"
            current_dir.mkdir(parents=True, exist_ok=True)
            metadata = ExtractorMetadata(
                id="site-1",
                name="Site 1",
                kind="news",
                version="1.0.0",
                status="enabled",
            )
            (current_dir / "extractor.py").write_text(
                f"{metadata_comment(metadata)}\nDEFAULT_URL = 'https://example.com'\n",
                encoding="utf-8",
            )
            (current_dir / "manifest.json").write_text(json.dumps({"id": "site-1"}), encoding="utf-8")

            workspace = prepare_repair_workspace(
                tasks_root=project_root / "agent_work" / "extractors",
                registry=ExtractorRegistry(project_root / "extractors"),
                source_id="site-1",
                task_id="site-1-20260706",
            )

            self.assertFalse(workspace.bootstrap)
            copied = workspace.work_dir / "current" / "extractor.py"
            self.assertTrue(copied.exists())
            self.assertIn("DEFAULT_URL", copied.read_text(encoding="utf-8"))

    def test_publish_repair_workspace_archives_previous_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            registry = ExtractorRegistry(project_root / "extractors")
            target_current = registry.root / "site-1" / "current"
            target_current.mkdir(parents=True, exist_ok=True)
            (target_current / "extractor.py").write_text("old\n", encoding="utf-8")

            new_current = project_root / "task" / "current"
            new_current.mkdir(parents=True, exist_ok=True)
            (new_current / "extractor.py").write_text("new\n", encoding="utf-8")

            published = publish_repair_workspace(
                registry=registry,
                source_id="site-1",
                current_dir=new_current,
                version_tag="20260706120000",
            )

            self.assertEqual(published, target_current)
            self.assertEqual((published / "extractor.py").read_text(encoding="utf-8"), "new\n")
            versioned = registry.root / "site-1" / "versions" / "20260706120000" / "extractor.py"
            self.assertEqual(versioned.read_text(encoding="utf-8"), "old\n")


if __name__ == "__main__":
    unittest.main()
