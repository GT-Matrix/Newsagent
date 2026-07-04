from __future__ import annotations

from typing import Any

from modnews.repository.cache import CacheRepository
from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.outputs import OutputRepository


class ArtifactsLocalMixin:
    def outputs_status(self) -> dict[str, Any]:
        return OutputRepository(self.project_root).state()

    def outputs_cat(self, key: str) -> dict[str, Any]:
        return OutputRepository(self.project_root).read_artifact(key)

    def cache_status(self) -> dict[str, Any]:
        return CacheRepository(self.project_root).state()

    def cache_clear(self, *, llm: bool, embedding: bool) -> dict[str, Any]:
        return {
            "ok": True,
            "removed": CacheRepository(self.project_root).clear(llm=llm, embedding=embedding),
            "outputs": self.outputs_status(),
        }

    def checkpoints_list(self, run_id: str | None = None) -> list[dict[str, Any]]:
        return CheckpointRepository(self.project_root).list(run_id)

    def checkpoint_publish(self, checkpoint_path: str) -> dict[str, Any]:
        checkpoint = CheckpointRepository(self.project_root).read(checkpoint_path)
        return {"ok": True, **OutputRepository(self.project_root).publish_from_checkpoint(checkpoint)}
