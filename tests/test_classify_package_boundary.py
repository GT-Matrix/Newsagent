from __future__ import annotations

import importlib
import importlib.util
import unittest


class ClassifyPackageBoundaryTest(unittest.TestCase):
    def test_legacy_clustered_tasks_module_is_not_importable(self) -> None:
        self.assertIsNone(importlib.util.find_spec("modnews.service.classify.clustered_tasks"))

    def test_legacy_relevance_modules_are_not_importable(self) -> None:
        self.assertIsNone(importlib.util.find_spec("modnews.service.classify.relevance"))
        self.assertIsNone(importlib.util.find_spec("modnews.service.classify.article"))

    def test_task_execution_module_exports_clustered_task_entrypoints(self) -> None:
        module = importlib.import_module("modnews.service.classify.task_execution")
        self.assertTrue(hasattr(module, "run_clustered_event_extraction_task"))
        self.assertTrue(hasattr(module, "run_clustered_event_merge_task"))
        self.assertTrue(hasattr(module, "REGISTERED_CLASSIFY_TASK_EXECUTORS"))

    def test_planner_does_not_export_legacy_whole_graph_helper(self) -> None:
        module = importlib.import_module("modnews.service.classify.planner")
        self.assertFalse(hasattr(module, "plan_clustered_classify_tasks"))

    def test_batch_compat_modules_are_explicit_shims(self) -> None:
        batch_tasks = importlib.import_module("modnews.service.classify.batch_tasks")
        llm_batch_registry = importlib.import_module("modnews.service.classify.llm_batch_registry")

        self.assertTrue(getattr(batch_tasks, "COMPATIBILITY_SHIM", False))
        self.assertTrue(getattr(llm_batch_registry, "COMPATIBILITY_SHIM", False))


if __name__ == "__main__":
    unittest.main()
