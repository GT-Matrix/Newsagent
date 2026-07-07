from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

import requests

from modnews.core.config import load_config
from modnews.core.context import PipelineContext
from modnews.service.classify.llm_client import LlmClient
from modnews.service.classify.retriever import EventVectorRetriever
from modnews.service.classify.runner import ClassifyRuntime, ClassifyStepResult
from modnews.service.classify.state import ClassifyState
from modnews.service.classify.task_result import publish_fixed_classify_outputs
from modnews.service.classify.steps import build_registered_classify_steps


class ClassifyFixedOutputsTest(unittest.TestCase):
    def test_steps_no_longer_write_fixed_outputs_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._runtime(Path(tmp), write_fixed_outputs=True)
            step = build_registered_classify_steps("start_checkpoint")[0]

            with patch("modnews.service.classify.steps.build_checkpoint_meta") as checkpoint_meta:
                checkpoint_meta.return_value = {"stage": "started"}
                result = step.run(ClassifyState(items=[], prepared=[]), runtime)

            checkpoint_meta.assert_called_once()
            self.assertIsInstance(result, ClassifyStepResult)
            self.assertEqual(result.stats["total_candidates"], 0)

    def test_publish_fixed_outputs_uses_run_result_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._runtime(Path(tmp), write_fixed_outputs=True)
            step = build_registered_classify_steps("start_checkpoint")[0]
            step_result = step.run(ClassifyState(items=[], prepared=[]), runtime)
            run_result = type("RunResult", (), {"state": step_result.state, "last_step_result": step_result})()

            with patch("modnews.service.classify.task_result.write_outputs") as write_outputs:
                publish_fixed_classify_outputs(config=runtime.config, run_result=run_result)

            write_outputs.assert_called_once()
            self.assertEqual(step_result.next_stage, "started")
            self.assertEqual(step_result.checkpoint_meta["stage"], "started")

    def _runtime(self, project_root: Path, *, write_fixed_outputs: bool) -> ClassifyRuntime:
        config_path = project_root / "config.json"
        config_path.write_text(json.dumps({}), encoding="utf-8")
        pipeline_config = load_config(str(config_path))
        config = pipeline_config.classification
        ctx = PipelineContext.create(pipeline_config)
        return ClassifyRuntime(
            ctx=ctx,
            config=config,
            client=LlmClient(config.llm, requests.Session()),
            retriever=EventVectorRetriever(config.embedding, requests.Session()),
            write_fixed_outputs=write_fixed_outputs,
        )


if __name__ == "__main__":
    unittest.main()
