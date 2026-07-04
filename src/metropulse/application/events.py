"""Minimal in-process async event bus.

The realtime engine publishes an event after every feed poll; the commuter
rule engine (and any future consumer) subscribes to it. This makes
notifications event-driven — evaluated exactly when new data arrives —
instead of polling the database on an unrelated timer.

Handlers run sequentially and are error-isolated: one failing subscriber
never breaks the publisher or its peers.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

EventHandler = Callable[[Any], Awaitable[None]]

FEED_UPDATED = "feed.updated"


class EventBus:
    """Topic-based publish/subscribe for coroutine handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Register a coroutine handler for a topic."""
        self._handlers.setdefault(topic, []).append(handler)

    def subscriber_count(self, topic: str) -> int:
        """Number of handlers registered for a topic."""
        return len(self._handlers.get(topic, []))

    async def publish(self, topic: str, payload: Any) -> None:
        """Invoke every handler for a topic with the payload.

        Handler exceptions are logged, never propagated.
        """
        for handler in self._handlers.get(topic, []):
            try:
                await handler(payload)
            except Exception:
                logger.exception(
                    "event handler %r failed for topic %s",
                    getattr(handler, "__qualname__", handler),
                    topic,
                )
