from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.bootstrap import configure_services
from modnews.repository.runs import RunRepository
from modnews.service.classify.io import resolve_input_path
from modnews.service.classify.planner import (
    build_clustered_event_extraction_task,
    build_clustered_event_merge_task,
)
from modnews.service.extraction.task_registry import REGISTERED_EXTRACTION_TASK_BY_TYPE
from modnews.service.ingest.registry import REGISTERED_INGEST_STEP_SPEC_BY_ID
from modnews.service.ingest.task_registry import REGISTERED_INGEST_TASK_BY_TYPE
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews.service.pipeline.steps import REGISTERED_PIPELINE_STEP_SPEC_BY_ID
from modnews.service.pipeline.task_registry import REGISTERED_PIPELINE_TASK_BY_TYPE
from modnews.service.pipeline.task_builder import build_report_generate_task
from modnews.service.report.planner import plan_report_tasks
from modnews.service.report.tasks import _resolve_report_input


class PipelineTaskGraphTest(unittest.TestCase):
    def test_pipeline_step_specs_are_registered_from_single_source(self) -> None:
        self.assertEqual(
            list(REGISTERED_PIPELINE_STEP_SPEC_BY_ID),
            ["pipeline_ingest", "pipeline_combine_ingest", "pipeline_classify", "pipeline_report"],
        )
        self.assertEqual(REGISTERED_PIPELINE_STEP_SPEC_BY_ID["pipeline_ingest"].planner_id, "ingest_root")
        self.assertEqual(
            REGISTERED_PIPELINE_STEP_SPEC_BY_ID["pipeline_classify"].concrete_step_ids,
            ("classify/clustered_event_extraction", "classify/clustered_event_merge"),
        )

    def test_pipeline_combine_task_definition_is_registered_from_single_source(self) -> None:
        spec = REGISTERED_PIPELINE_TASK_BY_TYPE["pipeline.combine_ingest"]

        self.assertEqual(spec.step_id, "pipeline/combine_ingest")
        self.assertEqual(spec.task_id_suffix, "combine-ingest")
        self.assertEqual(spec.concurrency_key_prefix, "pipeline")
        self.assertEqual(spec.max_concurrency, 1)

    def test_ingest_run_step_task_definition_is_registered_from_single_source(self) -> None:
        spec = REGISTERED_INGEST_TASK_BY_TYPE["ingest.run_step"]

        self.assertEqual(spec.step_id_prefix, "ingest")
        self.assertEqual(spec.task_id_prefix, "ingest")
        self.assertEqual(spec.concurrency_key_prefix, "ingest")
        self.assertEqual(spec.max_concurrency, 1)

    def test_ingest_step_registry_specs_are_registered_from_single_source(self) -> None:
        self.assertEqual(
            list(REGISTERED_INGEST_STEP_SPEC_BY_ID),
            ["rss", "newsnow", "site_lists"],
        )
        self.assertEqual(REGISTERED_INGEST_STEP_SPEC_BY_ID["rss"].factory.__name__, "RssStep")
        self.assertEqual(REGISTERED_INGEST_STEP_SPEC_BY_ID["site_lists"].factory.__name__, "SiteListsStep")

    def test_extraction_task_definitions_are_registered_from_single_source(self) -> None:
        web_source = REGISTERED_EXTRACTION_TASK_BY_TYPE["web_source.run"]
        repair = REGISTERED_EXTRACTION_TASK_BY_TYPE["extractor.repair.codex"]

        self.assertEqual(web_source.step_id_prefix, "ingest/site_lists")
        self.assertEqual(web_source.task_id_prefix, "web-source")
        self.assertEqual(web_source.concurrency_key_prefix, "web_source")
        self.assertEqual(web_source.max_attempts, 1)
        self.assertEqual(repair.step_id_prefix, "extractor/repair")
        self.assertEqual(repair.task_id_prefix, "repair")
        self.assertEqual(repair.concurrency_key_prefix, "extractor.repair")

    def test_pipeline_registry_registers_split_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            container = configure_services(Path(tmp))

            self.assertEqual(
                [step.id for step in container.pipeline_manager.steps],
                ["pipeline_ingest", "pipeline_combine_ingest", "pipeline_classify", "pipeline_report"],
            )

    def test_pipeline_registry_exposes_step_descriptors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            container = configure_services(Path(tmp))

            descriptors = container.pipeline_manager.describe_steps()

            self.assertEqual([item.step_id for item in descriptors], ["pipeline_ingest", "pipeline_combine_ingest", "pipeline_classify", "pipeline_report"])
            self.assertEqual(descriptors[0].group, "ingest")
            self.assertEqual(descriptors[0].kind, "root")
            self.assertEqual(descriptors[0].concrete_step_prefixes, ("ingest/",))
            self.assertEqual(descriptors[1].callback_handlers, ("completed", "failed", "blocked"))
            self.assertEqual(descriptors[1].depends_on, ("pipeline_ingest",))
            self.assertEqual(descriptors[1].followups[0].builder_id, "combine_ingest_for_run")
            self.assertEqual(descriptors[2].followups[0].task_type, "pipeline.combine_ingest")
            self.assertEqual(
                descriptors[2].concrete_step_ids,
                ("classify/clustered_event_extraction", "classify/clustered_event_merge"),
            )
            self.assertEqual(descriptors[3].group, "report")

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

    def test_report_task_definition_is_shared_between_pipeline_and_manual_planner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)

            followup_task = build_report_generate_task(
                run_id="run-1",
                project_root=str(project_root),
                config_path="runtime/config.json",
                depends_on=["classify-run-1-clustered-event-merge"],
            )
            manual_task = plan_report_tasks(
                project_root=project_root,
                input_path="output/events.json",
                run_id="run-1",
                output_dir="data/custom-output",
                date="2026-07-06",
                config="runtime/config.json",
            )[0]

            self.assertEqual(followup_task.type, "report.generate")
            self.assertEqual(followup_task.step_id, "report/generate")
            self.assertEqual(followup_task.id, "report-run-1-generate")
            self.assertEqual(followup_task.payload["input_path"], "__latest_classify_checkpoint__")
            self.assertEqual(followup_task.payload["output_dir"], "data/output")
            self.assertEqual(followup_task.depends_on, ["classify-run-1-clustered-event-merge"])

            self.assertEqual(manual_task.type, followup_task.type)
            self.assertEqual(manual_task.step_id, followup_task.step_id)
            self.assertEqual(manual_task.id, followup_task.id)
            self.assertEqual(manual_task.payload["config"], followup_task.payload["config"])
            self.assertEqual(manual_task.concurrency_key, followup_task.concurrency_key)
            self.assertEqual(manual_task.max_concurrency, followup_task.max_concurrency)

    def test_classify_task_definition_defaults_are_shared_by_pipeline_builder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)

            extraction = build_clustered_event_extraction_task(
                project_root=project_root,
                run_id="run-1",
                input_path=None,
                config="runtime/config.json",
            )
            merge = build_clustered_event_merge_task(
                project_root=project_root,
                run_id="run-1",
                input_path=None,
                config="runtime/config.json",
                depends_on=[extraction.id],
            )

            self.assertEqual(extraction.payload["input_path"], "__combined_ingest__")
            self.assertEqual(merge.payload["input_path"], "__combined_ingest__")
            self.assertEqual(extraction.concurrency_key, "classify")
            self.assertEqual(merge.max_concurrency, 1)


if __name__ == "__main__":
    unittest.main()
