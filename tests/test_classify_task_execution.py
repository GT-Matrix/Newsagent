from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modnews.core.config import load_config
from modnews.core.context import PipelineContext
from modnews.core.models import NewsItem
from modnews.bootstrap import configure_services
from modnews.service.classify.manual import run_classification
from modnews.service.classify.run_result import build_classify_step_result
from modnews.service.classify.runner import ClassifyRunResult, ClassifyStepResult
from modnews.service.classify.state import ClassifyState
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews.repository.runs import RunRepository
from modnews.service.classify.task_registry import get_registered_classify_task
from modnews.service.classify.steps import get_registered_classify_flow


class ClassifyTaskExecutionTest(unittest.TestCase):
    def test_build_classify_step_result_uses_shared_run_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(str(_write_config(Path(tmp))), project_root=Path(tmp)).classification
            item = NewsItem(platform="x", title="t", url="https://example.com", pubtime=None, scrape_date="2026-07-03")
            run_result = ClassifyRunResult(
                state=ClassifyState(items=[item], prepared=[]),
                last_step_result=ClassifyStepResult(
                    state=ClassifyState(items=[item], prepared=[]),
                    next_stage="completed",
                    stats={"item_count": 1, "event_count": 2, "discarded_count": 3, "merged_event_count": 4},
                ),
            )

            result = build_classify_step_result(config=config, run_result=run_result)

            self.assertEqual(result.step, "classify")
            self.assertEqual(result.item_count, 1)
            self.assertEqual(result.meta["event_count"], 2)
            self.assertEqual(result.meta["discarded_count"], 3)
            self.assertEqual(result.meta["merged_event_count"], 4)
            self.assertEqual(result.output_path, str(config.output_path))

    def test_run_classification_returns_shared_step_result_for_enabled_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            pipeline_config = load_config(str(_write_config(project_root)), project_root=project_root)
            item = NewsItem(platform="x", title="t", url="https://example.com", pubtime=None, scrape_date="2026-07-03")
            checkpoint_manager = CheckpointManager(project_root)
            container = configure_services(project_root)

            def extraction_executor(task):
                artifact = checkpoint_manager.write_artifact(
                    task.pipeline_run_id,
                    "classify/clustered_event_extraction",
                    task.id,
                    "classification_progress.json",
                    {"meta": {"stage": "after_clustered_event_extraction"}, "items": [item.to_dict()], "events": [], "discarded": []},
                )
                checkpoint = checkpoint_manager.write(
                    task.pipeline_run_id,
                    "classify/clustered_event_extraction",
                    task.id,
                    {
                        "run_id": task.pipeline_run_id,
                        "step_id": "classify/clustered_event_extraction",
                        "task_id": task.id,
                        "status": "succeeded",
                        "output_refs": {"classification_progress": str(artifact)},
                        "stats": {"item_count": 1, "event_count": 0, "discarded_count": 0, "merged_event_count": 0},
                        "error": None,
                    },
                )
                RunRepository(project_root).append_checkpoint(task.pipeline_run_id, checkpoint, create_payload={"source": "test"})
                return {"checkpoint_path": str(checkpoint), "stats": {"item_count": 1, "event_count": 0, "discarded_count": 0, "merged_event_count": 0}}

            def merge_executor(task):
                news_path = checkpoint_manager.write_artifact(
                    task.pipeline_run_id,
                    "classify/clustered_event_merge",
                    task.id,
                    "news_with_events.json",
                    [item.to_dict()],
                )
                events_path = checkpoint_manager.write_artifact(
                    task.pipeline_run_id,
                    "classify/clustered_event_merge",
                    task.id,
                    "events.json",
                    [],
                )
                discarded_path = checkpoint_manager.write_artifact(
                    task.pipeline_run_id,
                    "classify/clustered_event_merge",
                    task.id,
                    "discarded_news.json",
                    [],
                )
                progress_path = checkpoint_manager.write_artifact(
                    task.pipeline_run_id,
                    "classify/clustered_event_merge",
                    task.id,
                    "classification_progress.json",
                    {"meta": {"stage": "completed"}, "items": [item.to_dict()], "events": [], "discarded": []},
                )
                checkpoint = checkpoint_manager.write(
                    task.pipeline_run_id,
                    "classify/clustered_event_merge",
                    task.id,
                    {
                        "run_id": task.pipeline_run_id,
                        "step_id": "classify/clustered_event_merge",
                        "task_id": task.id,
                        "status": "succeeded",
                        "output_refs": {
                            "news_with_events": str(news_path),
                            "events": str(events_path),
                            "discarded_news": str(discarded_path),
                            "classification_progress": str(progress_path),
                        },
                        "stats": {"item_count": 1, "event_count": 0, "discarded_count": 0, "merged_event_count": 7},
                        "error": None,
                    },
                )
                RunRepository(project_root).append_checkpoint(task.pipeline_run_id, checkpoint, create_payload={"source": "test"})
                return {"checkpoint_path": str(checkpoint), "stats": {"item_count": 1, "event_count": 0, "discarded_count": 0, "merged_event_count": 7}}

            container.event_queue.register_executor("classify.clustered_event_extraction", extraction_executor)
            container.event_queue.register_executor("classify.clustered_event_merge", merge_executor)

            with patch("modnews.service.classify.manual.configure_services", return_value=container):
                items, events, step_result = run_classification(
                    PipelineContext.create(pipeline_config),
                    [item],
                    pipeline_config.classification,
                )

            self.assertEqual(items, [item])
            self.assertEqual(events, [])
            self.assertEqual(step_result.meta["merged_event_count"], 7)
            self.assertEqual(step_result.output_path, str(pipeline_config.classification.output_path))

    def test_manual_and_taskized_classify_paths_share_registered_flows(self) -> None:
        extraction_task = get_registered_classify_task("classify.clustered_event_extraction")
        merge_task = get_registered_classify_task("classify.clustered_event_merge")

        self.assertEqual(
            [step.name for step in get_registered_classify_flow("full").build_steps()],
            ["start_checkpoint", "clustered_event_extraction", "clustered_event_merge"],
        )
        self.assertEqual(extraction_task.node_stages, ("embedding", "extraction", "completed"))
        self.assertEqual(merge_task.node_stages, ("embedding", "merge", "completed"))

    def test_run_classification_short_circuits_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config_path = _write_config(project_root, classification={"enabled": False})
            pipeline_config = load_config(str(config_path), project_root=project_root)
            item = NewsItem(platform="x", title="t", url="https://example.com", pubtime=None, scrape_date="2026-07-03")

            items, events, step_result = run_classification(
                PipelineContext.create(pipeline_config),
                [item],
                pipeline_config.classification,
            )

            self.assertEqual(items, [item])
            self.assertEqual(events, [])
            self.assertEqual(step_result.meta["enabled"], False)


def _write_config(project_root: Path, **patch) -> Path:
    config_path = project_root / "config.json"
    config_path.write_text(json.dumps(patch), encoding="utf-8")
    return config_path


if __name__ == "__main__":
    unittest.main()
