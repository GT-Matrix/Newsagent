from __future__ import annotations

import importlib
import unittest


class ExtractionPackageBoundaryTest(unittest.TestCase):
    def test_repair_module_is_explicit_compatibility_shim(self) -> None:
        module = importlib.import_module("modnews.service.extraction.repair")
        manager_module = importlib.import_module("modnews.service.extraction.repair_manager")

        self.assertTrue(getattr(module, "COMPATIBILITY_SHIM", False))
        self.assertIs(module.RepairManager, manager_module.RepairManager)


if __name__ == "__main__":
    unittest.main()
