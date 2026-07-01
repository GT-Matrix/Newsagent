from __future__ import annotations

from abc import ABC, abstractmethod

from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import NewsItem, StepResult


class IngestStep(ABC):
    step_name: str

    def __init__(self, **options):
        self.options = options

    @abstractmethod
    def run(self, ctx: PipelineContext) -> tuple[list[NewsItem], StepResult]:
        raise NotImplementedError
