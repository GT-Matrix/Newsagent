from __future__ import annotations

from modnews.internal.service.ingest.registry import default_ingest_registry
from modnews.internal.service.pipeline.manager import PipelineManager


def register_pipeline_steps(manager: PipelineManager) -> None:
    """Register pipeline steps during application bootstrap.

    The legacy adapter still owns execution during this stage. Task-producing
    steps should be added here as they are migrated.
    """
    manager.ingest_registry = default_ingest_registry()
