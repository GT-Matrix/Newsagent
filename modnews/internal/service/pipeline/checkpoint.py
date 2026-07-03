from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.repository.checkpoints import CheckpointRepository


class CheckpointManager:
    def __init__(self, project_root: Path) -> None:
        self.repository = CheckpointRepository(project_root)

    def write(self, run_id: str, step_id: str, task_id: str, payload: dict[str, Any]) -> Path:
        return self.repository.write(run_id, step_id, task_id, payload)
