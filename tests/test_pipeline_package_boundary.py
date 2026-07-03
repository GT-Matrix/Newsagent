from __future__ import annotations

import importlib.util
import unittest

import modnews.service.pipeline as pipeline


class PipelinePackageBoundaryTest(unittest.TestCase):
    def test_legacy_pipeline_modules_are_not_importable(self) -> None:
        self.assertIsNone(importlib.util.find_spec("modnews.service.pipeline.compat"))
        self.assertIsNone(importlib.util.find_spec("modnews.service.pipeline.legacy"))
        self.assertIsNone(importlib.util.find_spec("modnews.service.pipeline.legacy_runner"))

    def test_pipeline_package_does_not_export_sync_runner(self) -> None:
        self.assertFalse(hasattr(pipeline, "run_pipeline"))
        self.assertTrue(hasattr(pipeline, "PipelineManager"))


if __name__ == "__main__":
    unittest.main()
