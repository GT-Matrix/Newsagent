from __future__ import annotations

from typing import Protocol

from .runner import ClassifyRunResult, ClassifyRuntime, ClassifyStepResult
from .state import ClassifyState

COMPATIBILITY_SHIM = True


class ClassifyStep(Protocol):
    name: str
    output_stage: str

    def should_run(self, state: ClassifyState) -> bool:
        ...

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyStepResult:
        ...


class ClassifyStepObserver(Protocol):
    def on_skip(self, *, step_name: str, state: ClassifyState) -> None:
        ...

    def on_start(self, *, step_name: str, output_stage: str, state: ClassifyState) -> None:
        ...

    def on_done(self, *, step_name: str, state: ClassifyState) -> None:
        ...


class ClassifyStepRunner:
    def __init__(self, steps: list[ClassifyStep], observer: ClassifyStepObserver | None = None) -> None:
        self.steps = steps
        self.observer = observer

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyRunResult:
        last_result: ClassifyStepResult | None = None
        for step in self.steps:
            if not step.should_run(state):
                if self.observer is not None:
                    self.observer.on_skip(step_name=step.name, state=state)
                continue
            if self.observer is not None:
                self.observer.on_start(step_name=step.name, output_stage=step.output_stage, state=state)
            result = step.run(state, runtime)
            state = result.state
            if result.next_stage is not None:
                state.stage = result.next_stage
            if self.observer is not None:
                self.observer.on_done(step_name=step.name, state=state)
            last_result = result
        return ClassifyRunResult(state=state, last_step_result=last_result)
