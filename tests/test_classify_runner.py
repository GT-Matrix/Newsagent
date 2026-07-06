from __future__ import annotations

import unittest

from modnews.service.classify.runner import ClassifyStepResult, ClassifyStepRunner
from modnews.service.classify.state import ClassifyState


class _TransitionStep:
    name = "transition"
    output_stage = "after_transition"

    def should_run(self, state: ClassifyState) -> bool:
        return state.stage == "started"

    def run(self, state: ClassifyState, runtime) -> ClassifyStepResult:  # noqa: ANN001
        state.processed_candidates = 3
        return ClassifyStepResult(state=state, next_stage="after_transition")


class _NoopStep:
    name = "noop"
    output_stage = "ignored"

    def should_run(self, state: ClassifyState) -> bool:
        return state.stage == "after_transition"

    def run(self, state: ClassifyState, runtime) -> ClassifyStepResult:  # noqa: ANN001
        return ClassifyStepResult(state=state, next_stage=None)


class ClassifyRunnerTest(unittest.TestCase):
    def test_runner_applies_explicit_next_stage_from_step_result(self) -> None:
        runner = ClassifyStepRunner([_TransitionStep(), _NoopStep()])
        state = runner.run(ClassifyState(items=[], prepared=[]), runtime=None)  # type: ignore[arg-type]

        self.assertEqual(state.stage, "after_transition")
        self.assertEqual(state.processed_candidates, 3)


if __name__ == "__main__":
    unittest.main()
