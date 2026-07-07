from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modnews.service.ingest.steps.newsnow import NewsNowStep
from modnews.service.ingest.steps.rss import RssStep
from modnews.service.ingest.steps.site_lists import SiteListsStep


@dataclass(frozen=True, slots=True)
class RegisteredIngestStepSpec:
    step_id: str
    factory: type[Any]


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


REGISTERED_INGEST_STEP_SPECS: tuple[RegisteredIngestStepSpec, ...] = (
    RegisteredIngestStepSpec(step_id="rss", factory=RssStep),
    RegisteredIngestStepSpec(step_id="newsnow", factory=NewsNowStep),
    RegisteredIngestStepSpec(step_id="site_lists", factory=SiteListsStep),
)

REGISTERED_INGEST_STEP_SPEC_BY_ID: dict[str, RegisteredIngestStepSpec] = {
    spec.step_id: spec
    for spec in REGISTERED_INGEST_STEP_SPECS
}


def build_ingest_registry() -> IngestStepRegistry:
    registry = IngestStepRegistry()
    for spec in REGISTERED_INGEST_STEP_SPECS:
        registry.register(spec.step_id, spec.factory)
    return registry


DEFAULT_INGEST_REGISTRY = build_ingest_registry()
STEP_FACTORIES = dict(DEFAULT_INGEST_REGISTRY.factories)


def default_ingest_registry() -> IngestStepRegistry:
    return DEFAULT_INGEST_REGISTRY


__all__ = [
    "DEFAULT_INGEST_REGISTRY",
    "IngestStepRegistry",
    "RegisteredIngestStepSpec",
    "REGISTERED_INGEST_STEP_SPECS",
    "REGISTERED_INGEST_STEP_SPEC_BY_ID",
    "STEP_FACTORIES",
    "build_ingest_registry",
    "default_ingest_registry",
]
