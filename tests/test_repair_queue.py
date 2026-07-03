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

            with (
                patch("modnews.service.extraction.repair.RepairManager.run_task", return_value=None),
                patch(
                    "modnews.service.extraction.repair.RepairManager.get_task",
                    return_value={"id": "source-1-20200101000000", "source_id": "source-1", "status": "succeeded"},
                ),
            ):
                result = client.repair_create({"source_id": "source-1", "reason": "test repair"})

            self.assertTrue(result["ok"])
            self.assertEqual(result["task"]["type"], "extractor.repair.codex")
            self.assertEqual(result["task"]["state"], "succeeded")
            self.assertEqual(result["task"]["result"]["repair_task"]["status"], "succeeded")
            self.assertIn("task.completed", {row["type"] for row in result["task"]["logs"]})

    def test_repair_create_can_queue_without_auto_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            result = client.repair_create({"source_id": "source-1", "reason": "test repair", "auto_start": False})

            self.assertTrue(result["ok"])
            self.assertIsNone(result["task"])
            self.assertEqual(result["item"]["status"], "queued")


if __name__ == "__main__":
    unittest.main()

