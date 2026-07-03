from __future__ import annotations

import importlib.util
import unittest


class ReportPackageBoundaryTest(unittest.TestCase):
    def test_legacy_src_package_is_not_importable(self) -> None:
        self.assertIsNone(importlib.util.find_spec("src"))

    def test_report_service_package_is_importable(self) -> None:
        self.assertIsNotNone(importlib.util.find_spec("modnews.service.report"))


if __name__ == "__main__":
    unittest.main()
