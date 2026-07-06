from __future__ import annotations

from dataclasses import dataclass

from modnews.core.progress import emit
from modnews.service.classify.state import ClassifyState


@dataclass(slots=True)
class EmittingClassifyStepObserver:
    def on_skip(self, *, step_name: str, state: ClassifyState) -> None:
        emit("step_skip", step=step_name, stage=state.stage)

    def on_start(self, *, step_name: str, output_stage: str, state: ClassifyState) -> None:
        emit("step_start", step=step_name, stage=state.stage, output_stage=output_stage)

    def on_done(self, *, step_name: str, state: ClassifyState) -> None:
        emit("step_done", step=step_name, stage=state.stage)
