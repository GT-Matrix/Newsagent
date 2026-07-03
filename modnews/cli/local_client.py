from __future__ import annotations

from pathlib import Path

from modnews.bootstrap import configure_services
from modnews.cli.local.artifacts import ArtifactsLocalMixin
from modnews.cli.local.extraction import ExtractionLocalMixin
from modnews.cli.local.queue import QueueLocalMixin
from modnews.cli.local.runtime import RuntimeLocalMixin
from modnews.cli.local.runs import RunsLocalMixin


class LocalClient(
    RuntimeLocalMixin,
    QueueLocalMixin,
    RunsLocalMixin,
    ExtractionLocalMixin,
    ArtifactsLocalMixin,
):
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.container = configure_services(self.project_root)
