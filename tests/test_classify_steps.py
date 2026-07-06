from __future__ import annotations

import unittest

from modnews.service.classify.steps import (
    REGISTERED_CLASSIFY_STEP_SPEC_BY_NAME,
    build_extraction_task_steps,
    build_full_classify_steps,
    build_merge_task_steps,
)


class ClassifyStepsTest(unittest.TestCase):
    def test_registered_step_specs_are_single_source_for_step_builders(self) -> None:
        self.assertEqual(
            sorted(REGISTERED_CLASSIFY_STEP_SPEC_BY_NAME),
            ["clustered_event_extraction", "clustered_event_merge", "start_checkpoint"],
        )
        self.assertEqual([step.name for step in build_full_classify_steps()], ["start_checkpoint", "clustered_event_extraction", "clustered_event_merge"])
        self.assertEqual([step.name for step in build_extraction_task_steps()], ["start_checkpoint", "clustered_event_extraction"])
        self.assertEqual([step.name for step in build_merge_task_steps()], ["clustered_event_merge"])


if __name__ == "__main__":
    unittest.main()
