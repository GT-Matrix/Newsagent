from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.service.extraction.repair_state_ops import (
    apply_repair_final_result,
    fail_repair_task,
    queue_repair_task,
    start_repair_task,
)
from modnews.service.extraction.repair_store import RepairTask


class RepairStateOpsTest(unittest.TestCase):
    def _task(self, root: Path) -> RepairTask:
        work_dir = root / "site-1" / "task-1"
        work_dir.mkdir(parents=True, exist_ok=True)
        return RepairTask(
            id="task-1",
            source_id="site-1",
            status="failed",
            work_dir=work_dir,
            created_at="2026-07-06T00:00:00+08:00",
            updated_at="2026-07-06T00:00:00+08:00",
            log_path=work_dir / "codex.jsonl",
            result_path=work_dir / "result.json",
            command=[],
            error="old error",
        )

    def test_queue_repair_task_resets_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = self._task(Path(tmp))

            updated = queue_repair_task(task)

            self.assertEqual(updated.status, "queued")
            self.assertIsNone(updated.error)

    def test_start_repair_task_sets_running_and_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = self._task(Path(tmp))

            updated = start_repair_task(task, ["codex", "exec"])

            self.assertEqual(updated.status, "running")
            self.assertIsNone(updated.error)
            self.assertEqual(updated.command, ["codex", "exec"])

    def test_fail_repair_task_sets_failed_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = self._task(Path(tmp))

            updated = fail_repair_task(task, "boom")

            self.assertEqual(updated.status, "failed")
            self.assertEqual(updated.error, "boom")

    def test_apply_repair_final_result_marks_blocked_and_writes_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = self._task(Path(tmp))

            updated = apply_repair_final_result(
                task,
                {"status": "skipped_unrepairable", "summary": "captcha required", "next_steps": ["manual review"]},
            )

            self.assertEqual(updated.status, "blocked")
            self.assertEqual(updated.error, "captcha required")
            blocked_payload = json.loads((updated.work_dir / "blocked.json").read_text(encoding="utf-8"))
            self.assertEqual(blocked_payload["status"], "blocked")
            self.assertEqual(blocked_payload["next_steps"], ["manual review"])

    def test_apply_repair_final_result_marks_succeeded_for_fixed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task = self._task(Path(tmp))

            updated = apply_repair_final_result(task, {"status": "fixed", "summary": "done"})

            self.assertEqual(updated.status, "succeeded")
            self.assertIsNone(updated.error)


if __name__ == "__main__":
    unittest.main()
