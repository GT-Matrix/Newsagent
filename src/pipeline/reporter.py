"""Compatibility exports for report rendering and section assignment."""

from modnews.service.report.reporter import (
    ASSET_TYPES,
    ASSET_WORDS,
    DEEP_ASSET_EXCLUDE,
    POLICY_TYPES,
    TOP_TYPE_LIMITS,
    WATCH_TYPES,
    assign_report_sections,
    build_debug_report_markdown,
    build_report_markdown,
    report_candidates_payload,
    review_candidates_payload,
)

__all__ = [
    "ASSET_TYPES",
    "ASSET_WORDS",
    "DEEP_ASSET_EXCLUDE",
    "POLICY_TYPES",
    "TOP_TYPE_LIMITS",
    "WATCH_TYPES",
    "assign_report_sections",
    "build_debug_report_markdown",
    "build_report_markdown",
    "report_candidates_payload",
    "review_candidates_payload",
]

