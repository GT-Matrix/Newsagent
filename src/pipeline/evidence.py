"""Compatibility exports for report evidence enrichment."""

from modnews.service.report.evidence import (
    EvidenceItem,
    MAX_SOURCES_PER_EVENT,
    MAX_TEXT_CHARS,
    OFFICIAL_DOMAINS,
    REQUEST_TIMEOUT_SECONDS,
    enrich_report_evidence,
)

__all__ = [
    "EvidenceItem",
    "MAX_SOURCES_PER_EVENT",
    "MAX_TEXT_CHARS",
    "OFFICIAL_DOMAINS",
    "REQUEST_TIMEOUT_SECONDS",
    "enrich_report_evidence",
]

