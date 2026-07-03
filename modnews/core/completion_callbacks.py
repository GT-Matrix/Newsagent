from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from modnews.core.events import EventRouter

CompletionCallback = Callable[[dict[str, Any]], dict[str, Any] | None]


@dataclass(slots=True)
class CompletionCallbackRegistry:
    _callbacks: dict[str, list[CompletionCallback]] = field(default_factory=lambda: defaultdict(list))

    def register(self, event_type: str, callback: CompletionCallback) -> None:
        self._callbacks[event_type].append(callback)

    def bind(self, router: EventRouter) -> None:
        for event_type, callbacks in self._callbacks.items():
            for callback in callbacks:
                router.on(event_type, callback)

    def list(self) -> dict[str, int]:
        return {event_type: len(callbacks) for event_type, callbacks in self._callbacks.items()}
