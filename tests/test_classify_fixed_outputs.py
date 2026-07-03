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
from modnews.service.classify.runner import ClassifyRuntime
from modnews.service.classify.state import ClassifyState
from modnews.service.classify.steps import StartCheckpointStep


class ClassifyFixedOutputsTest(unittest.TestCase):
    def test_steps_skip_fixed_outputs_when_runtime_disables_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._runtime(Path(tmp), write_fixed_outputs=False)

            with patch("modnews.service.classify.steps.write_outputs") as write_outputs:
                StartCheckpointStep().run(ClassifyState(items=[], prepared=[]), runtime)

            write_outputs.assert_not_called()

    def test_steps_write_fixed_outputs_for_standalone_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self._runtime(Path(tmp), write_fixed_outputs=True)

            with patch("modnews.service.classify.steps.write_outputs") as write_outputs:
                StartCheckpointStep().run(ClassifyState(items=[], prepared=[]), runtime)

            write_outputs.assert_called_once()

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
