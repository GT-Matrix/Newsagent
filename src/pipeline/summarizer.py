"""Compatibility exports for the report summarizer stage."""

from modnews.service.report.stages.summarizer import (
    ACTION_PATTERNS,
    SUMMARY_REWRITES,
    TITLE_REWRITES,
    TYPE_NOUNS,
    summarize_event,
)

__all__ = [
    "ACTION_PATTERNS",
    "SUMMARY_REWRITES",
    "TITLE_REWRITES",
    "TYPE_NOUNS",
    "summarize_event",
]
