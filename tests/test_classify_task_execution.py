from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modnews.core.config import load_config
from modnews.core.context import PipelineContext
from modnews.core.models import NewsItem
from modnews.service.classify.run_result import build_classify_step_result
from modnews.service.classify.runner import ClassifyRunResult, ClassifyStepResult
from modnews.service.classify.state import ClassifyState
from modnews.service.classify.task_execution import run_classification


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
            state = ClassifyState(items=[item], prepared=[])
            run_result = ClassifyRunResult(
                state=state,
                last_step_result=ClassifyStepResult(
                    state=state,
                    next_stage="completed",
                    stats={"item_count": 1, "event_count": 0, "discarded_count": 0, "merged_event_count": 7},
                ),
            )

            with patch("modnews.service.classify.task_execution.build_classify_state_from_items", return_value=state):
                with patch("modnews.service.classify.task_execution.build_classify_runtime_for_context", return_value=object()):
                    with patch("modnews.service.classify.task_execution.ClassifyStepRunner.run", return_value=run_result):
                        items, events, step_result = run_classification(
                            PipelineContext.create(pipeline_config),
                            [item],
                            pipeline_config.classification,
                        )

            self.assertEqual(items, [item])
            self.assertEqual(events, [])
            self.assertEqual(step_result.meta["merged_event_count"], 7)
            self.assertEqual(step_result.output_path, str(pipeline_config.classification.output_path))

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
