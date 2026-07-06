from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modnews.cli.local_client import LocalClient


class RepairQueueTest(unittest.TestCase):
    def test_repair_create_runs_codex_repair_through_event_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            def write_log(self, task_id: str) -> None:
                task = self._load_task(task_id)
                task.log_path.write_text("codex line 1\ncodex line 2\n", encoding="utf-8")
                task.status = "succeeded"
                task.error = None
                self._save_task(task)

            with patch("modnews.service.extraction.repair.RepairManager.run_task", new=write_log):
                result = client.repair_create({"source_id": "source-1", "reason": "test repair"})

            self.assertTrue(result["ok"])
            self.assertEqual(result["task"]["type"], "extractor.repair.codex")
            self.assertEqual(result["task"]["state"], "succeeded")
            self.assertEqual(result["task"]["result"]["repair_task"]["status"], "succeeded")
            self.assertIn("codex line 2", result["task"]["result"]["codex_log_tail"])
            self.assertIn("task.completed", {row["type"] for row in result["task"]["logs"]})
            self.assertIn("progress.codex_repair_log", {row["type"] for row in result["task"]["logs"]})

    def test_repair_create_can_queue_without_auto_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            result = client.repair_create({"source_id": "source-1", "reason": "test repair", "auto_start": False})

            self.assertTrue(result["ok"])
            self.assertIsNone(result["task"])
            self.assertEqual(result["item"]["status"], "queued")

    def test_repair_task_detail_reads_log_tail_via_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            created = client.repair_create({"source_id": "source-1", "reason": "test repair", "auto_start": False})
            task_id = created["item"]["id"]
            log_path = Path(created["item"]["log_path"])
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("header\nbody line 1\nbody line 2\n", encoding="utf-8")

            task = client.repair_task(task_id)

            self.assertEqual(task["id"], task_id)
            self.assertIn("body line 2", task["log_tail"])


if __name__ == "__main__":
    unittest.main()
