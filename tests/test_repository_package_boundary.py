from __future__ import annotations

import importlib
import unittest


class RepositoryPackageBoundaryTest(unittest.TestCase):
    def test_runtime_config_module_is_explicit_compatibility_shim(self) -> None:
        module = importlib.import_module("modnews.repository.runtime_config")
        repository_module = importlib.import_module("modnews.repository.runtime_config_repository")
        store_module = importlib.import_module("modnews.repository.runtime_config_store")

        self.assertTrue(getattr(module, "COMPATIBILITY_SHIM", False))
        self.assertIs(module.RuntimeConfigRepository, repository_module.RuntimeConfigRepository)
        self.assertIs(module.RuntimeConfigStore, store_module.RuntimeConfigStore)
        self.assertIs(module.runtime_config_store, store_module.runtime_config_store)

    def test_event_log_module_is_explicit_compatibility_shim(self) -> None:
        module = importlib.import_module("modnews.repository.event_log")
        jsonl_module = importlib.import_module("modnews.repository.event_jsonl")

        self.assertTrue(getattr(module, "COMPATIBILITY_SHIM", False))
        self.assertIs(module.append_event, jsonl_module.append_event)
        self.assertIs(module.read_events, jsonl_module.read_events)


if __name__ == "__main__":
    unittest.main()
