from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.bootstrap import configure_services
from modnews.core.task import TaskEvent
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
from modnews.service.pipeline.read_model_support import task_detail_kind, task_log_kind, task_title
from modnews.service.pipeline.steps import REGISTERED_PIPELINE_STEP_SPEC_BY_ID
from modnews.service.pipeline.task_domain_view import (
    REGISTERED_TASK_DOMAIN_VIEW_BY_ID,
    resolve_task_domain_view,
)
from modnews.service.pipeline.task_presentation import (
    REGISTERED_TASK_PRESENTATION_BY_ID,
    resolve_task_presentation,
)
from modnews.service.pipeline.task_read_model_meta import (
    REGISTERED_TASK_READ_MODEL_META_BY_ID,
    resolve_task_read_model_meta,
)
from modnews.service.pipeline.task_summary import (
    REGISTERED_TASK_SUMMARY_BY_ID,
    resolve_task_summary,
)
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

    def test_task_presentation_specs_are_registered_from_single_source(self) -> None:
        self.assertEqual(
            list(REGISTERED_TASK_PRESENTATION_BY_ID),
            [
                "pipeline.combine_ingest",
                "report.generate",
                "web_source.run",
                "extractor.repair.codex",
                "classify.clustered_event_extraction",
                "classify.clustered_event_merge",
                "classify.embedding",
                "classify.batch_relevance",
                "classify.clustered_event_extraction.batch",
                "classify.clustered_event_merge.batch",
                "classify.batch",
                "ingest.task",
            ],
        )
        self.assertEqual(REGISTERED_TASK_PRESENTATION_BY_ID["report.generate"].log_kind, "report")
        self.assertEqual(REGISTERED_TASK_PRESENTATION_BY_ID["pipeline.combine_ingest"].detail_kind, "ingest_task")

    def test_task_presentation_registry_drives_titles_and_kinds(self) -> None:
        batch_task = TaskEvent(
            id="classify.clustered_event_extraction.batch:group-1:1",
            type="classify.clustered_event_extraction.batch",
            payload={"batch": {"batch_index": 1, "batch_count": 3}},
        )
        report_task = TaskEvent(id="report-run-1-generate", type="report.generate")
        ingest_task = TaskEvent(id="ingest-rss", type="ingest.run_step")
        web_task = TaskEvent(
            id="web-source-run-1-site-1",
            type="web_source.run",
            payload={"source_id": "site-1"},
        )

        self.assertEqual(resolve_task_presentation(batch_task).id, "classify.clustered_event_extraction.batch")
        self.assertEqual(task_title(batch_task), "classify.clustered_event_extraction.batch [1/3]")
        self.assertEqual(task_log_kind(batch_task), "classify")
        self.assertEqual(task_detail_kind(batch_task), "classify_task")

        self.assertEqual(task_title(report_task), "Generate report")
        self.assertEqual(task_log_kind(report_task), "report")
        self.assertEqual(task_detail_kind(report_task), "report_task")

        self.assertEqual(task_title(ingest_task), "Run ingest task run_step")
        self.assertEqual(task_log_kind(ingest_task), "task")
        self.assertEqual(task_detail_kind(ingest_task), "ingest_task")

        self.assertEqual(task_title(web_task), "Run web source site-1")
        self.assertEqual(task_log_kind(web_task), "web_job")
        self.assertEqual(task_detail_kind(web_task), "web_source_task")

    def test_task_domain_view_specs_are_registered_from_single_source(self) -> None:
        self.assertEqual(
            list(REGISTERED_TASK_DOMAIN_VIEW_BY_ID),
            [
                "web_source.run",
                "extractor.repair.codex",
                "classify.task",
                "report.generate",
                "pipeline.combine_ingest",
                "ingest.task",
            ],
        )
        self.assertEqual(REGISTERED_TASK_DOMAIN_VIEW_BY_ID["classify.task"].builder_id, "classify")
        self.assertEqual(REGISTERED_TASK_DOMAIN_VIEW_BY_ID["report.generate"].builder_id, "report")

    def test_task_domain_view_registry_resolves_specific_and_prefix_matches(self) -> None:
        classify_task = TaskEvent(id="classify-1", type="classify.clustered_event_merge.batch")
        report_task = TaskEvent(id="report-1", type="report.generate")
        ingest_task = TaskEvent(id="ingest-1", type="ingest.run_step")
        fallback_task = TaskEvent(id="diag-1", type="diagnostic.echo")

        self.assertEqual(resolve_task_domain_view(classify_task).id, "classify.task")
        self.assertEqual(resolve_task_domain_view(report_task).id, "report.generate")
        self.assertEqual(resolve_task_domain_view(ingest_task).id, "ingest.task")
        self.assertIsNone(resolve_task_domain_view(fallback_task))

    def test_task_read_model_meta_specs_are_registered_from_single_source(self) -> None:
        self.assertEqual(
            list(REGISTERED_TASK_READ_MODEL_META_BY_ID),
            [
                "classify.embedding",
                "classify.batch_relevance",
                "classify.clustered_event_extraction.batch",
                "classify.clustered_event_merge.batch",
                "classify.clustered_event_extraction",
                "classify.clustered_event_merge",
                "classify.task",
                "report.generate",
                "pipeline.combine_ingest",
            ],
        )
        self.assertEqual(
            REGISTERED_TASK_READ_MODEL_META_BY_ID["report.generate"].publish_targets,
            (
                ("report_markdown", "report_markdown"),
                ("report_debug_markdown", "report_debug_markdown"),
                ("report_events", "report_events"),
                ("report_trend_summary", "report_trend_summary"),
            ),
        )
        self.assertEqual(
            REGISTERED_TASK_READ_MODEL_META_BY_ID["classify.clustered_event_merge.batch"].classify_task_kind,
            "clustered_event_merge_batch",
        )

    def test_task_read_model_meta_registry_resolves_specific_and_prefix_matches(self) -> None:
        classify_batch = TaskEvent(id="classify-1", type="classify.clustered_event_merge.batch")
        classify_other = TaskEvent(id="classify-2", type="classify.custom")
        report_task = TaskEvent(id="report-1", type="report.generate")
        combine_task = TaskEvent(id="combine-1", type="pipeline.combine_ingest")
        fallback_task = TaskEvent(id="diag-1", type="diagnostic.echo")

        self.assertEqual(resolve_task_read_model_meta(classify_batch).id, "classify.clustered_event_merge.batch")
        self.assertEqual(resolve_task_read_model_meta(classify_other).id, "classify.task")
        self.assertEqual(resolve_task_read_model_meta(report_task).id, "report.generate")
        self.assertEqual(resolve_task_read_model_meta(combine_task).id, "pipeline.combine_ingest")
        self.assertIsNone(resolve_task_read_model_meta(fallback_task))

    def test_task_summary_specs_are_registered_from_single_source(self) -> None:
        self.assertEqual(
            list(REGISTERED_TASK_SUMMARY_BY_ID),
            ["report.generate", "web_source.run"],
        )
        self.assertEqual(REGISTERED_TASK_SUMMARY_BY_ID["report.generate"].builder_id, "report")
        self.assertEqual(REGISTERED_TASK_SUMMARY_BY_ID["web_source.run"].builder_id, "web_source")

    def test_task_summary_registry_resolves_specific_matches(self) -> None:
        report_task = TaskEvent(id="report-1", type="report.generate")
        web_task = TaskEvent(id="web-1", type="web_source.run")
        fallback_task = TaskEvent(id="diag-1", type="diagnostic.echo")

        self.assertEqual(resolve_task_summary(report_task).id, "report.generate")
        self.assertEqual(resolve_task_summary(web_task).id, "web_source.run")
        self.assertIsNone(resolve_task_summary(fallback_task))

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
