from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


EventHandler = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class EventRouter:
    _handlers: dict[str, list[EventHandler]] = field(default_factory=lambda: defaultdict(list))

    def on(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def dispatch(self, event_type: str, payload: dict[str, Any]) -> None:
        for handler in self._handlers.get(event_type, []):
            handler(payload)
