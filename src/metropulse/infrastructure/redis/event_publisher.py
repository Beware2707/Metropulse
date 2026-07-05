"""Publisher for typed domain events onto the internal Redis event stream.

Separate from the ``mp:updates`` diff stream: diffs are the WS-gateway
transport (full train states, high volume), while ``mp:events`` carries
compact typed facts for internal consumers — analytics pipelines, audit,
future services. Publishing is strictly best-effort: a Redis blip must never
fail the business transaction that raised the event.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from redis.asyncio import Redis

from metropulse.domain.events import DomainEvent, event_name, parse_event, to_payload
from metropulse.metrics import metrics

logger = logging.getLogger(__name__)

EVENTS_STREAM = "mp:events"
_EVENTS_MAXLEN = 8192


class RedisDomainEventPublisher:
    """Appends domain events to the ``mp:events`` stream (best-effort)."""

    def __init__(self, redis: Redis, stream: str = EVENTS_STREAM) -> None:
        self._redis = redis
        self._stream = stream

    async def publish(self, event: DomainEvent) -> bool:
        """Publish one event; returns False (and logs) on failure."""
        try:
            await self._redis.xadd(
                self._stream,
                {"data": json.dumps(to_payload(event))},
                maxlen=_EVENTS_MAXLEN,
                approximate=True,
            )
        except Exception:
            logger.exception("failed to publish domain event %s", event_name(event))
            return False
        metrics.inc("metropulse_events_published_total")
        return True


def parse_stream_event(payload: dict[str, Any]) -> DomainEvent | None:
    """Parse a consumed stream entry (the JSON envelope) into a typed event."""
    return parse_event(payload)
