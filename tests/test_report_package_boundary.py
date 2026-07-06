from __future__ import annotations

import importlib
import importlib.util
import unittest


class ReportPackageBoundaryTest(unittest.TestCase):
    def test_legacy_src_package_is_not_importable(self) -> None:
        self.assertIsNone(importlib.util.find_spec("src"))

    def test_report_service_package_is_importable(self) -> None:
        self.assertIsNotNone(importlib.util.find_spec("modnews.service.report"))

    def test_report_package_does_not_export_execution_entrypoints(self) -> None:
        package = importlib.import_module("modnews.service.report")
        execution = importlib.import_module("modnews.service.report.execution")

        self.assertFalse(hasattr(package, "generate_report"))
        self.assertFalse(hasattr(package, "run_pipeline"))
        self.assertTrue(hasattr(execution, "generate_report"))


if __name__ == "__main__":
    unittest.main()
