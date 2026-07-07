from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modnews.cli.local_client import LocalClient
from modnews.core.task import TaskBlocked
from modnews.service.extraction.repair_runtime_facade import RepairRuntimeFacade
from modnews.service.extraction.repair_store import RepairTaskStore
from modnews.service.extraction.repair_task_result import build_repair_task_result


class RepairQueueTest(unittest.TestCase):
    def test_repair_runtime_facade_create_task_reuses_queue_runtime_submission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            facade = RepairRuntimeFacade(
                project_root=client.project_root,
                queue=client.container.event_queue,
                queue_show=client.queue_show,
            )

            def write_log(self, task_id: str):
                task = self._load_task(task_id)
                task.log_path.write_text("codex line 1\ncodex line 2\n", encoding="utf-8")
                task.status = "succeeded"
                task.error = None
                self._save_task(task)
                return task

            def finalize(self, task_id: str):
                return self._load_task(task_id)

            with patch("modnews.service.extraction.repair_manager.RepairManager.run_task_once", new=write_log), patch(
                "modnews.service.extraction.repair_manager.RepairManager.finalize_task",
                new=finalize,
            ):
                result = facade.create_task({"source_id": "source-1", "reason": "test repair"})

            self.assertTrue(result["ok"])
            self.assertEqual(result["task"]["type"], "extractor.repair.codex")
            self.assertEqual(result["task"]["state"], "succeeded")
            self.assertEqual(result["item"]["source_id"], "source-1")

    def test_repair_create_runs_codex_repair_through_event_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            def write_log(self, task_id: str):
                task = self._load_task(task_id)
                task.log_path.write_text("codex line 1\ncodex line 2\n", encoding="utf-8")
                task.status = "succeeded"
                task.error = None
                self._save_task(task)
                return task

            def finalize(self, task_id: str):
                return self._load_task(task_id)

            with patch("modnews.service.extraction.repair_manager.RepairManager.run_task_once", new=write_log), patch(
                "modnews.service.extraction.repair_manager.RepairManager.finalize_task",
                new=finalize,
            ):
                result = client.repair_create({"source_id": "source-1", "reason": "test repair"})

            self.assertTrue(result["ok"])
            self.assertEqual(result["task"]["type"], "extractor.repair.codex")
            self.assertEqual(result["task"]["state"], "succeeded")
            self.assertEqual(result["task"]["result"]["repair_task"]["status"], "succeeded")
            self.assertIn("codex line 2", result["task"]["result"]["codex_log_tail"])
            self.assertIn("task.completed", {row["type"] for row in result["task"]["logs"]})
            self.assertIn("progress.codex_repair_log", {row["type"] for row in result["task"]["logs"]})

    def test_repair_parent_task_blocks_when_exec_child_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            created = client.repair_create({"source_id": "source-1", "reason": "test repair", "auto_start": False})
            repair_task_id = created["item"]["id"]

            def blocked(self, task_id: str):
                task = self._load_task(task_id)
                task.status = "blocked"
                task.error = "captcha required"
                self._save_task(task)
                return task

            with patch("modnews.service.extraction.repair_manager.RepairManager.run_task_once", new=blocked):
                result = client.repair_retry(repair_task_id)

            self.assertTrue(result["ok"])
            self.assertEqual(result["task"]["type"], "extractor.repair.codex")
            self.assertEqual(result["task"]["state"], "blocked")
            self.assertIn("captcha required", result["task"]["result"]["blocked_reason"])

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

    def test_repair_store_builds_codex_log_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            created = client.repair_create({"source_id": "source-1", "reason": "test repair", "auto_start": False})
            task_id = created["item"]["id"]
            log_path = Path(created["item"]["log_path"])
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("header\nbody line 1\nbody line 2\n", encoding="utf-8")

            task_store = RepairTaskStore(log_path.parent.parent.parent)
            log_summary = task_store.codex_log_summary(task_id, max_chars=20)

            self.assertEqual(log_summary["codex_log_path"], str(log_path))
            self.assertIn("body line 2", log_summary["codex_log_tail"])
            self.assertGreater(log_summary["codex_log_bytes"], 0)

    def test_repair_task_result_helper_maps_blocked_and_failed_status(self) -> None:
        with self.assertRaises(TaskBlocked):
            build_repair_task_result(
                {"id": "task-1", "status": "blocked", "error": "captcha required"},
                {"codex_log_path": "/tmp/log.txt", "codex_log_tail": "", "codex_log_bytes": 0},
            )

        with self.assertRaises(RuntimeError):
            build_repair_task_result(
                {"id": "task-1", "status": "failed", "error": "broken extractor"},
                {"codex_log_path": "/tmp/log.txt", "codex_log_tail": "", "codex_log_bytes": 0},
            )

        result = build_repair_task_result(
            {"id": "task-1", "status": "succeeded", "source_id": "source-1"},
            {"codex_log_path": "/tmp/log.txt", "codex_log_tail": "ok", "codex_log_bytes": 2},
        )
        self.assertEqual(result["repair_task"]["status"], "succeeded")
        self.assertEqual(result["codex_log_tail"], "ok")


if __name__ == "__main__":
    unittest.main()
