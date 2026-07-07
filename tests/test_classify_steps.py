from __future__ import annotations

import unittest

from modnews.service.classify.steps import (
    COMPATIBILITY_SHIM,
    REGISTERED_CLASSIFY_FLOW_BY_NAME,
    REGISTERED_CLASSIFY_STEP_SPEC_BY_NAME,
    get_registered_classify_flow,
)


class ClassifyStepsTest(unittest.TestCase):
    def test_registered_step_specs_are_single_source_for_step_builders(self) -> None:
        self.assertTrue(COMPATIBILITY_SHIM)
        self.assertEqual(
            sorted(REGISTERED_CLASSIFY_STEP_SPEC_BY_NAME),
            ["clustered_event_extraction", "clustered_event_merge", "start_checkpoint"],
        )
        self.assertEqual(
            sorted(REGISTERED_CLASSIFY_FLOW_BY_NAME),
            ["clustered_event_extraction_task", "clustered_event_merge_task", "full"],
        )
        self.assertEqual(
            [step.name for step in get_registered_classify_flow("full").build_steps()],
            ["start_checkpoint", "clustered_event_extraction", "clustered_event_merge"],
        )
        self.assertEqual(
            [step.name for step in get_registered_classify_flow("clustered_event_extraction_task").build_steps()],
            ["start_checkpoint", "clustered_event_extraction"],
        )
        self.assertEqual(
            [step.name for step in get_registered_classify_flow("clustered_event_merge_task").build_steps()],
            ["clustered_event_merge"],
        )


if __name__ == "__main__":
    unittest.main()
