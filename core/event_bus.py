import asyncio
from collections import defaultdict
from typing import Awaitable, Callable

import structlog

from models import Event, EventType

Subscriber = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Subscriber]] = defaultdict(list)
        self._history: list[Event] = []
        self._max_history: int = 1000
        self._logger = structlog.get_logger(__name__)

    def subscribe(self, event_type: EventType, handler: Subscriber) -> None:
        self._subscribers[event_type].append(handler)
        self._logger.debug("subscriber_added", event_type=event_type.value)

    def unsubscribe(self, event_type: EventType, handler: Subscriber) -> None:
        self._subscribers[event_type].remove(handler)

    async def publish(self, event: Event) -> None:
        self._logger.debug("event_published", event_type=event.type.value)
        self._record(event)
        handlers = self._subscribers.get(event.type, [])
        if not handlers:
            return
        results = await asyncio.gather(
            *(h(event) for h in handlers),
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self._logger.error(
                    "handler_error",
                    handler=handlers[i].__qualname__,
                    error=str(result),
                )

    def _record(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_history(self, event_type: EventType | None = None) -> list[Event]:
        if event_type is None:
            return list(self._history)
        return [e for e in self._history if e.type == event_type]

    @property
    def subscriber_count(self) -> int:
        return sum(len(v) for v in self._subscribers.values())
