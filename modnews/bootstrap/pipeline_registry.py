from __future__ import annotations

from modnews.service.ingest.registry import default_ingest_registry
from modnews.service.pipeline.manager import PipelineManager
from modnews.service.pipeline.steps import build_registered_pipeline_steps


def register_pipeline_steps(manager: PipelineManager) -> None:
    """Register pipeline steps during application bootstrap.

    Bootstrap owns the wiring between pipeline planning and concrete service
    task executors so the manager does not import ingest/classify modules.
    """
    manager.ingest_registry = default_ingest_registry()
    for step in build_registered_pipeline_steps():
        manager.register_step(step)
