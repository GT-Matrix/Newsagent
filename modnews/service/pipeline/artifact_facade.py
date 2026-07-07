from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.outputs import OutputRepository
from modnews.service.pipeline.read_model_support import (
    attach_checkpoint_callback_summaries,
    normalize_checkpoints,
)


@dataclass(slots=True)
class PipelineArtifactFacade:
    project_root: Path

    def checkpoints(self, run_id: str | None = None) -> list[dict[str, Any]]:
        return attach_checkpoint_callback_summaries(
            self.project_root,
            normalize_checkpoints(CheckpointRepository(self.project_root).list(run_id)),
        )

    def publish_checkpoint(self, checkpoint_path: str) -> dict[str, Any]:
        checkpoint = CheckpointRepository(self.project_root).read(checkpoint_path)
        return {"ok": True, **OutputRepository(self.project_root).publish_from_checkpoint(checkpoint)}
