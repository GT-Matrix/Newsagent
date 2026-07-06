from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews.service.report.task_result import build_report_task_stats, persist_report_task_result
from modnews.service.report.task_runtime import (
    build_report_task_runtime,
    resolve_report_config_path,
    resolve_report_input,
    resolve_report_output_dir,
)


class _FakeEvent:
    def __init__(self, include: bool, with_sources: bool) -> None:
        self.should_include_report = include
        self.source_items = [{"id": "x"}] if with_sources else []


class ReportTaskRuntimeTest(unittest.TestCase):
    def test_build_runtime_resolves_relative_output_dir_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            task = TaskEvent(
                id="report-1",
                type="report.generate",
                pipeline_run_id="run-1",
                payload={
                    "project_root": str(project_root),
                    "run_id": "run-1",
                    "input_path": "output/events.json",
                    "output_dir": "data/custom-report",
                    "config": "runtime/config.json",
                },
            )

            runtime = build_report_task_runtime(task)

            self.assertEqual(runtime.project_root, project_root.resolve())
            self.assertEqual(runtime.run_id, "run-1")
            self.assertEqual(runtime.input_path, (project_root / "output" / "events.json").resolve())
            self.assertEqual(runtime.output_dir, (project_root / "data" / "custom-report").resolve())
            self.assertEqual(runtime.config_path, (project_root / "runtime" / "config.json").resolve())

    def test_resolve_report_input_uses_latest_classify_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            runs = RunRepository(project_root)
            checkpoints = CheckpointManager(project_root)
            artifact_path = checkpoints.write_artifact(
                "run-1",
                "classify/clustered_event_merge",
                "task-1",
                "classification_progress.json",
                {"items": [], "events": [], "discarded": []},
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
                resolve_report_input(
                    TaskEvent(id="task-1", type="report.generate", payload={"input_path": "__latest_classify_checkpoint__"}),
                    project_root,
                    "run-1",
                ),
                checkpoint_path.resolve(),
            )

    def test_build_report_task_stats_counts_selected_and_sourced_events(self) -> None:
        stats = build_report_task_stats(
            [
                _FakeEvent(include=True, with_sources=True),
                _FakeEvent(include=False, with_sources=True),
                _FakeEvent(include=True, with_sources=False),
            ]
        )

        self.assertEqual(stats, {"event_count": 3, "selected_count": 2, "events_with_sources": 2})

    def test_persist_report_task_result_writes_checkpoint_and_run_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            runs = RunRepository(project_root)
            runs.create("run-1", {})
            output_dir = project_root / "data" / "output"
            output_dir.mkdir(parents=True, exist_ok=True)

            result = persist_report_task_result(
                project_root=project_root,
                run_id="run-1",
                task_id="report-1",
                input_path=project_root / "output" / "events.json",
                output_dir=output_dir,
                stats={"event_count": 3, "selected_count": 2, "events_with_sources": 1},
            )

            checkpoint_path = Path(str(result["checkpoint_path"]))
            payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["step_id"], "report/generate")
            self.assertEqual(payload["stats"]["event_count"], 3)
            self.assertEqual(Path(payload["output_refs"]["report_markdown"]).name, "daily_report.md")
            self.assertEqual(RunRepository(project_root).get("run-1")["checkpoints"], [str(checkpoint_path)])


if __name__ == "__main__":
    unittest.main()
