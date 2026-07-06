from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.core.task import TaskEvent
from modnews.repository.checkpoints import CheckpointRepository
from modnews.service.pipeline.run_state_views import (
    build_pipeline_step_snapshots,
    build_step_snapshots,
    load_checkpoints,
    merge_pipeline_callback_events,
    restore_pipeline_descriptors,
)
from modnews.service.pipeline.steps import build_registered_pipeline_steps


class PipelineRunStateViewsTest(unittest.TestCase):
    def test_build_step_snapshots_merges_task_checkpoint_and_existing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            artifact = CheckpointRepository(project_root).write_artifact(
                "run-1",
                "ingest/rss",
                "task-1",
                "items.json",
                [{"title": "A"}],
            )
            CheckpointRepository(project_root).write(
                "run-1",
                "ingest/rss",
                "task-1",
                {
                    "status": "succeeded",
                    "stats": {"item_count": 1},
                    "output_refs": {"items": str(artifact)},
                },
            )
            tasks = [
                TaskEvent(id="task-1", type="diagnostic.echo", step_id="ingest/rss", state="succeeded"),
                TaskEvent(id="task-2", type="diagnostic.echo", step_id="pipeline/combine_ingest", depends_on=["task-1"], state="queued"),
            ]

            snapshots = build_step_snapshots(
                tasks,
                load_checkpoints(project_root, "run-1"),
                existing=[{"step_id": "pipeline/combine_ingest", "callback_events": [{"kind": "existing"}]}],
            )

            ingest = next(item for item in snapshots if item["step_id"] == "ingest/rss")
            combine = next(item for item in snapshots if item["step_id"] == "pipeline/combine_ingest")
            self.assertEqual(ingest["status"], "succeeded")
            self.assertEqual(ingest["stats"]["item_count"], 1)
            self.assertEqual(ingest["artifacts"][0]["name"], "items")
            self.assertEqual(combine["depends_on"], ["ingest/rss"])
            self.assertEqual(combine["callback_events"], [{"kind": "existing"}])

    def test_build_pipeline_step_snapshots_restores_descriptor_metadata(self) -> None:
        descriptors = [step.describe() for step in build_registered_pipeline_steps()]
        pipeline_steps = build_pipeline_step_snapshots(
            [{"step_id": "report/generate", "status": "succeeded", "task_ids": ["report-1"], "queued_task_ids": [], "completed_task_ids": ["report-1"], "blocked_task_ids": [], "skipped_task_ids": [], "failed_task_ids": [], "checkpoint_count": 0, "artifacts": [], "stats": {}, "depends_on": []}],
            run_payload={},
            descriptors=descriptors,
            existing=[{"step_id": "pipeline_report", "callback_events": [{"kind": "existing"}]}],
        )

        report_step = next(item for item in pipeline_steps if item["step_id"] == "pipeline_report")
        self.assertEqual(report_step["group"], "report")
        self.assertEqual(report_step["callback_events"], [{"kind": "existing"}])

    def test_restore_pipeline_descriptors_and_merge_callback_history(self) -> None:
        descriptors = restore_pipeline_descriptors(
            [
                {
                    "step_id": "pipeline_report",
                    "title": "Report Followups",
                    "group": "report",
                    "kind": "followup",
                    "depends_on": ["pipeline_classify"],
                    "callback_handlers": ["completed"],
                    "followups": [{"trigger": "done", "builder_id": "report_after", "task_type": "report.generate"}],
                    "concrete_step_ids": ["report/generate"],
                }
            ]
        )
        merged = merge_pipeline_callback_events(
            [{"step_id": "pipeline_report", "callback_events": [{"kind": "old"}]}],
            [{"step_id": "pipeline_report", "kind": "new"}],
        )

        self.assertEqual(descriptors[0].step_id, "pipeline_report")
        self.assertEqual(descriptors[0].followups[0].task_type, "report.generate")
        self.assertEqual(merged[0]["callback_events"], [{"kind": "old"}, {"step_id": "pipeline_report", "kind": "new"}])


if __name__ == "__main__":
    unittest.main()
