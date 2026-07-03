from __future__ import annotations

from modnews.core.events import EventRouter


def register_event_handlers(router: EventRouter) -> None:
    """Register default event callbacks.

    The first migration stage keeps legacy execution paths, so no callbacks are
    required yet. New task-based services should register their completion
    handlers here instead of wiring them from route modules.
    """
