from __future__ import annotations

import importlib
import unittest


class IngestPackageBoundaryTest(unittest.TestCase):
    def test_ingest_package_does_not_export_sync_stage_runner(self) -> None:
        package = importlib.import_module("modnews.service.ingest")
        stage = importlib.import_module("modnews.service.ingest.stage")

        self.assertFalse(hasattr(package, "run_ingest"))
        self.assertTrue(hasattr(stage, "run_ingest"))

    def test_ingest_entrypoints_module_exports_manual_task_entrypoint(self) -> None:
        entrypoints = importlib.import_module("modnews.service.ingest.entrypoints")

        self.assertTrue(hasattr(entrypoints, "run_ingest_step_tasks"))


if __name__ == "__main__":
    unittest.main()
