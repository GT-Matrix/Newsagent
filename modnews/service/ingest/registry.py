from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modnews.service.ingest.steps.newsnow import NewsNowStep
from modnews.service.ingest.steps.rss import RssStep
from modnews.service.ingest.steps.site_lists import SiteListsStep


@dataclass(slots=True)
class IngestStepRegistry:
    factories: dict[str, type[Any]] = field(default_factory=dict)

    def register(self, step_id: str, factory: type[Any]) -> None:
        self.factories[step_id] = factory

    def get(self, step_id: str) -> type[Any]:
        try:
            return self.factories[step_id]
        except KeyError as exc:
            raise ValueError(f"Unsupported ingest step: {step_id}") from exc

    def list(self) -> list[str]:
        return sorted(self.factories)


def default_ingest_registry() -> IngestStepRegistry:
    registry = IngestStepRegistry()
    registry.register("rss", RssStep)
    registry.register("newsnow", NewsNowStep)
    registry.register("site_lists", SiteListsStep)
    return registry


STEP_FACTORIES = default_ingest_registry().factories

__all__ = ["IngestStepRegistry", "STEP_FACTORIES", "default_ingest_registry"]
