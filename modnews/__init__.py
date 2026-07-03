"""Public package for the ModNews application."""

from modnews.service.pipeline.legacy import run_pipeline, run_pipeline_from_path

__all__ = ["run_pipeline", "run_pipeline_from_path"]
