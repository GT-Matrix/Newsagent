from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.core.models import EventRecord, NewsItem
from modnews.service.classify.checkpoint import write_run_output_artifacts
from modnews.service.classify.io import resolve_resume_checkpoint_path, resolve_task_resume_checkpoint_path
from modnews.service.classify.types import DiscardedRecord
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews.repository.runs import RunRepository


class ClassifyCheckpointArtifactsTest(unittest.TestCase):
    def test_writes_classify_artifacts_into_checkpoint_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            manager = CheckpointManager(project_root)
            item = NewsItem(platform="x", title="t", url="https://example.com", pubtime=None, scrape_date="2026-07-03")
            event = EventRecord(
                event_id="e1",
                event_label="label",
                member_count=1,
                platforms=["x"],
                latest_pubtime=None,
                representative_titles=["t"],
            )
            discarded = [DiscardedRecord(index=1, title="drop", platform="x", stage="test", reason="no")]

            refs = write_run_output_artifacts(
                manager,
                "run-1",
                "classify/test",
                "task-1",
                [item],
                [event],
                discarded,
                {"stage": "test"},
            )
            checkpoint_path = manager.write(
                "run-1",
                "classify/test",
                "task-1",
                {
                    "run_id": "run-1",
                    "step_id": "classify/test",
                    "task_id": "task-1",
                    "status": "succeeded",
                    "output_refs": refs,
                    "stats": {},
                    "error": None,
                },
            )

            self.assertEqual({Path(value).parent for value in refs.values()}, {checkpoint_path.parent})
            self.assertEqual(json.loads(Path(refs["news_with_events"]).read_text(encoding="utf-8"))[0]["title"], "t")
            self.assertEqual(json.loads(Path(refs["classification_progress"]).read_text(encoding="utf-8"))["meta"]["stage"], "test")

    def test_resume_checkpoint_prefers_run_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            manager = CheckpointManager(project_root)
            runs = RunRepository(project_root)
            runs.create("run-1", {})
            fixed_path = project_root / "output" / "classification_progress.json"
            fixed_path.parent.mkdir(parents=True)
            fixed_path.write_text(json.dumps({"meta": {"stage": "fixed"}}, ensure_ascii=False), encoding="utf-8")

            refs = manager.write_artifact(
                "run-1",
                "classify/test",
                "task-1",
                "classification_progress.json",
                {"meta": {"stage": "artifact"}},
            )
            checkpoint_path = manager.write(
                "run-1",
                "classify/test",
                "task-1",
                {
                    "run_id": "run-1",
                    "step_id": "classify/test",
                    "task_id": "task-1",
                    "status": "succeeded",
                    "output_refs": {"classification_progress": str(refs)},
                    "stats": {},
                    "error": None,
                },
            )
            runs.update("run-1", checkpoints=[str(checkpoint_path)])

            self.assertEqual(resolve_resume_checkpoint_path(project_root, "run-1", fixed_path), refs.resolve())

    def test_resume_checkpoint_falls_back_to_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            fixed_path = project_root / "output" / "classification_progress.json"
            fixed_path.parent.mkdir(parents=True)
            fixed_path.write_text(json.dumps({"meta": {"stage": "fixed"}}, ensure_ascii=False), encoding="utf-8")

            self.assertEqual(resolve_resume_checkpoint_path(project_root, "missing-run", fixed_path), fixed_path)

    def test_task_resume_checkpoint_does_not_fall_back_to_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            fixed_path = project_root / "output" / "classification_progress.json"
            fixed_path.parent.mkdir(parents=True)
            fixed_path.write_text(json.dumps({"meta": {"stage": "fixed"}}, ensure_ascii=False), encoding="utf-8")

            self.assertIsNone(resolve_task_resume_checkpoint_path(project_root, "missing-run"))


if __name__ == "__main__":
    unittest.main()
