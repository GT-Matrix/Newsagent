"""Compatibility exports for the report classifier stage."""

from modnews.service.report.stages.classifier import (
    DEEP_ASSET_TYPES_STRICT,
    DEEP_ASSET_WORDS,
    INSIGHT_WORDS,
    NEWS_OVERRIDE_TYPES,
    classify_event,
)

__all__ = [
    "DEEP_ASSET_TYPES_STRICT",
    "DEEP_ASSET_WORDS",
    "INSIGHT_WORDS",
    "NEWS_OVERRIDE_TYPES",
    "classify_event",
]
