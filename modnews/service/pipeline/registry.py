from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PipelineRegistry:
    steps: dict[str, Any] = field(default_factory=dict)

    def register(self, step: Any) -> None:
        self.steps[step.id] = step

    def list(self) -> list[Any]:
        return list(self.steps.values())
