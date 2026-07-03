"""Compatibility exports for the report scorer stage."""

from modnews.service.report.stages.scorer import (
    ACTIONABLE_TYPES,
    ACTIONABLE_WORDS,
    FOLLOW_UP_WORDS,
    NOVELTY_WORDS,
    STRATEGIC_FOCUS_BOOSTS,
    STRATEGIC_FOCUS_KEYWORDS,
    score_event,
)

__all__ = [
    "ACTIONABLE_TYPES",
    "ACTIONABLE_WORDS",
    "FOLLOW_UP_WORDS",
    "NOVELTY_WORDS",
    "STRATEGIC_FOCUS_BOOSTS",
    "STRATEGIC_FOCUS_KEYWORDS",
    "score_event",
]

