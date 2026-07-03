from __future__ import annotations

from typing import Any


def run_modnews(config_path: str | None = None) -> Any:
    """Run the integrated ingest/classify pipeline."""
    from modnews.service.pipeline.compat import run_pipeline_from_path

    return run_pipeline_from_path(config_path)
