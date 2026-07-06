from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.bootstrap import configure_services
from modnews.core.task import TaskEvent


class PipelineTaskGraphTest(unittest.TestCase):
    def test_pipeline_registry_registers_split_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            container = configure_services(Path(tmp))

            self.assertEqual(
                [step.id for step in container.pipeline_manager.steps],
                ["pipeline_ingest", "pipeline_combine_ingest", "pipeline_classify", "pipeline_report"],
            )

    def test_classify_completion_patches_report_input_to_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            container = configure_services(Path(tmp))
            queue = container.event_queue
            manager = container.pipeline_manager
            report_task = TaskEvent(
                id="report-run-1-generate",
                type="report.generate",
                pipeline_run_id="run-1",
                step_id="report/generate",
                payload={"project_root": tmp, "input_path": "__latest_classify_checkpoint__"},
            )
            queue.register(report_task)

            manager.on_task_completed(
                {
                    "task": {
                        "id": "classify-run-1-clustered-event-merge",
                        "type": "classify.clustered_event_merge",
                        "pipeline_run_id": "run-1",
                        "payload": {"project_root": tmp},
                    },
                    "result": {"checkpoint_path": "/tmp/classify/checkpoint.json"},
                },
            )

            self.assertEqual(queue.get(report_task.id).payload["input_path"], "/tmp/classify/checkpoint.json")

    def test_combine_ingest_completion_patches_classify_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            container = configure_services(Path(tmp))
            queue = container.event_queue
            manager = container.pipeline_manager
            classify_task = TaskEvent(
                id="classify-run-1-clustered-event-extraction",
                type="classify.clustered_event_extraction",
                pipeline_run_id="run-1",
                step_id="classify/clustered_event_extraction",
                payload={"project_root": tmp, "input_path": "__combined_ingest__"},
            )
            queue.register(classify_task)

            manager.on_task_completed(
                {
                    "task": {
                        "id": "pipeline-run-1-combine-ingest",
                        "type": "pipeline.combine_ingest",
                        "pipeline_run_id": "run-1",
                        "payload": {"project_root": tmp},
                    },
                    "result": {"combined_ingest_path": "/tmp/combined/items.json"},
                }
            )

            self.assertEqual(queue.get(classify_task.id).payload["input_path"], "/tmp/combined/items.json")


if __name__ == "__main__":
    unittest.main()
