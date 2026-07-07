from __future__ import annotations

import importlib
import importlib.util
import unittest


class ClassifyPackageBoundaryTest(unittest.TestCase):
    def test_classify_package_does_not_export_manual_entrypoint(self) -> None:
        package = importlib.import_module("modnews.service.classify")
        manual = importlib.import_module("modnews.service.classify.manual")

        self.assertFalse(hasattr(package, "run_classification"))
        self.assertTrue(hasattr(manual, "run_classification"))

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
        self.assertFalse(hasattr(module, "run_classification"))

    def test_manual_module_exports_manual_classify_entrypoint(self) -> None:
        module = importlib.import_module("modnews.service.classify.manual")
        self.assertTrue(hasattr(module, "run_classification"))

    def test_planner_does_not_export_legacy_whole_graph_helper(self) -> None:
        module = importlib.import_module("modnews.service.classify.planner")
        self.assertFalse(hasattr(module, "plan_clustered_classify_tasks"))

    def test_steps_module_does_not_export_legacy_convenience_builders(self) -> None:
        module = importlib.import_module("modnews.service.classify.steps")
        self.assertTrue(getattr(module, "COMPATIBILITY_SHIM", False))
        self.assertFalse(hasattr(module, "build_full_classify_steps"))
        self.assertFalse(hasattr(module, "build_extraction_task_steps"))
        self.assertFalse(hasattr(module, "build_merge_task_steps"))
        self.assertFalse(hasattr(module, "StartCheckpointStep"))
        self.assertFalse(hasattr(module, "ClusteredEventExtractionStep"))
        self.assertFalse(hasattr(module, "ClusteredEventMergeStep"))

    def test_step_observer_module_is_not_importable(self) -> None:
        self.assertIsNone(importlib.util.find_spec("modnews.service.classify.step_observer"))

    def test_batch_compat_modules_are_explicit_shims(self) -> None:
        batch_tasks = importlib.import_module("modnews.service.classify.batch_tasks")
        llm_batch_registry = importlib.import_module("modnews.service.classify.llm_batch_registry")

        self.assertTrue(getattr(batch_tasks, "COMPATIBILITY_SHIM", False))
        self.assertTrue(getattr(llm_batch_registry, "COMPATIBILITY_SHIM", False))
        self.assertIs(batch_tasks.run_clustered_event_extraction_batch_item, batch_tasks.run_registered_llm_batch_item)
        self.assertIs(batch_tasks.run_clustered_event_merge_batch_item, batch_tasks.run_registered_llm_batch_item)


if __name__ == "__main__":
    unittest.main()
