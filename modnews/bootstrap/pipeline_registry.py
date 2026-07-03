from __future__ import annotations

from modnews.service.ingest.registry import default_ingest_registry
from modnews.service.pipeline.manager import PipelineManager
from modnews.service.pipeline.planner import IngestClassifyPipelineStep


def register_pipeline_steps(manager: PipelineManager) -> None:
    """Register pipeline steps during application bootstrap.

    The legacy adapter still owns execution during this stage. Task-producing
    steps should be added here as they are migrated.
    """
    manager.ingest_registry = default_ingest_registry()
    manager.register_step(IngestClassifyPipelineStep())
