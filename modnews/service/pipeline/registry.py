from __future__ import annotations

from dataclasses import dataclass, field

from modnews.service.pipeline.step import PipelineStep


@dataclass(slots=True)
class PipelineRegistry:
    steps: dict[str, PipelineStep] = field(default_factory=dict)

    def register(self, step: PipelineStep) -> None:
        self.steps[step.id] = step

    def list(self) -> list[PipelineStep]:
        return list(self.steps.values())
