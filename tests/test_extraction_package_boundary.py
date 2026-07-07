from __future__ import annotations

import importlib
import unittest


class ExtractionPackageBoundaryTest(unittest.TestCase):
    def test_repair_module_is_explicit_compatibility_shim(self) -> None:
        module = importlib.import_module("modnews.service.extraction.repair")
        manager_module = importlib.import_module("modnews.service.extraction.repair_manager")

        self.assertTrue(getattr(module, "COMPATIBILITY_SHIM", False))
        self.assertIs(module.RepairManager, manager_module.RepairManager)

    def test_runner_module_is_explicit_compatibility_shim(self) -> None:
        module = importlib.import_module("modnews.service.extraction.runner")
        runner_module = importlib.import_module("modnews.service.extraction.web_runner")

        self.assertTrue(getattr(module, "COMPATIBILITY_SHIM", False))
        self.assertIs(module.run_extractor, runner_module.run_extractor)
        self.assertIs(module.write_json, runner_module.write_json)


if __name__ == "__main__":
    unittest.main()
