from __future__ import annotations

from typing import Any

from modnews.repository.cache import CacheRepository
from modnews.repository.outputs import OutputRepository
from modnews.service.pipeline.artifact_facade import PipelineArtifactFacade


class ArtifactsLocalMixin:
    def _pipeline_artifacts(self) -> PipelineArtifactFacade:
        return PipelineArtifactFacade(self.project_root)

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
        return self._pipeline_artifacts().checkpoints(run_id)

    def checkpoint_publish(self, checkpoint_path: str) -> dict[str, Any]:
        return self._pipeline_artifacts().publish_checkpoint(checkpoint_path)
