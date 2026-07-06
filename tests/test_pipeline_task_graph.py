from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.bootstrap import configure_services
from modnews.repository.runs import RunRepository
from modnews.service.classify.io import resolve_input_path
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews.service.report.tasks import _resolve_report_input


class PipelineTaskGraphTest(unittest.TestCase):
    def test_pipeline_registry_registers_split_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            container = configure_services(Path(tmp))

            self.assertEqual(
                [step.id for step in container.pipeline_manager.steps],
                ["pipeline_ingest", "pipeline_combine_ingest", "pipeline_classify", "pipeline_report"],
            )

    def test_report_input_placeholder_resolves_latest_classify_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            runs = RunRepository(project_root)
            checkpoints = CheckpointManager(project_root)
            artifact_path = checkpoints.write_artifact(
                "run-1",
                "classify/clustered_event_merge",
                "task-1",
                "classification_progress.json",
                {"items": [], "events": [], "discarded": [], "meta": {"stage": "after_clustered_event_merge"}},
            )
            checkpoint_path = checkpoints.write(
                "run-1",
                "classify/clustered_event_merge",
                "task-1",
                {
                    "run_id": "run-1",
                    "step_id": "classify/clustered_event_merge",
                    "task_id": "task-1",
                    "status": "succeeded",
                    "output_refs": {"classification_progress": str(artifact_path)},
                    "stats": {},
                    "error": None,
                },
            )
            runs.create("run-1", {})
            runs.append_checkpoint("run-1", checkpoint_path)

            self.assertEqual(
                _resolve_report_input(
                    type("Task", (), {"payload": {"input_path": "__latest_classify_checkpoint__"}})(),
                    project_root,
                    "run-1",
                ),
                checkpoint_path.resolve(),
            )

    def test_classify_input_placeholder_resolves_combined_ingest_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            combined_dir = project_root / "runtime" / "checkpoints" / "run-1" / "pipeline" / "combine_ingest" / "task-1"
            combined_dir.mkdir(parents=True)
            items_path = combined_dir / "items.json"
            items_path.write_text("[]", encoding="utf-8")
            runs = RunRepository(project_root)
            runs.create("run-1", {})
            runs.update("run-1", combined_ingest_path=str(items_path))

            self.assertEqual(
                resolve_input_path(
                    project_root,
                    "run-1",
                    "__combined_ingest__",
                    project_root / "fallback.json",
                ),
                items_path.resolve(),
            )


if __name__ == "__main__":
    unittest.main()
