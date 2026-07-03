from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TaskEvent:
    id: str
    type: str
    pipeline_run_id: str | None = None
    step_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    concurrency_key: str | None = None
    max_concurrency: int | None = None
    depends_on: list[str] = field(default_factory=list)
    checkpoint_policy: str = "default"
    state: str = "queued"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
