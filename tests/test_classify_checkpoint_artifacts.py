from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.core.models import EventRecord, NewsItem
from modnews.service.classify.checkpoint import write_run_output_artifacts
from modnews.service.classify.types import DiscardedRecord
from modnews.service.pipeline.checkpoint import CheckpointManager


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


if __name__ == "__main__":
    unittest.main()
