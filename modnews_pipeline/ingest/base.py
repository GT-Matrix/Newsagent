from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import subprocess

from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import NewsItem, StepResult


@dataclass(slots=True)
class CurlResponse:
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def raise_for_status(self) -> None:
        return None


def fetch_via_curl(url: str, *, user_agent: str, timeout_seconds: int = 30) -> CurlResponse:
    """Use curl/HTTP1.1 only after requests cannot complete a TLS handshake."""
    completed = subprocess.run(
        [
            "curl",
            "--fail",
            "--location",
            "--http1.1",
            "--silent",
            "--show-error",
            "--connect-timeout",
            str(min(timeout_seconds, 15)),
            "--max-time",
            str(timeout_seconds),
            "--user-agent",
            user_agent,
            url,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return CurlResponse(content=completed.stdout)


class IngestStep(ABC):
    step_name: str

    def __init__(self, **options):
        self.options = options

    @abstractmethod
    def run(self, ctx: PipelineContext) -> tuple[list[NewsItem], StepResult]:
        raise NotImplementedError
