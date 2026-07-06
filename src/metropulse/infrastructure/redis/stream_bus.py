"""Redis Streams consumer for the feed-update event pipeline.

Unlike pub/sub, streams are durable: events survive consumer restarts, each
consumer group receives every event independently, and unacknowledged
entries are redelivered to the (stable-named) consumer after a crash.

Reads are short non-blocking polls rather than blocking XREADGROUP calls so
the implementation behaves identically on redis-py and fakeredis, and task
cancellation is always prompt.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

import asyncio

from redis.asyncio import Redis
from redis.exceptions import ResponseError

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class RedisStreamConsumer:
    """A consumer-group member processing JSON events from one stream."""

    def __init__(
        self,
        redis: Redis,
        stream: str,
        group: str,
        consumer_name: str,
        *,
        batch_size: int = 32,
        idle_sleep_seconds: float = 0.1,
    ) -> None:
        self._redis = redis
        self._stream = stream
        self._group = group
        self._consumer = consumer_name
        self._batch = batch_size
        self._idle_sleep = idle_sleep_seconds

    @property
    def group(self) -> str:
        """The consumer group this member belongs to."""
        return self._group

    async def ensure_group(self) -> None:
        """Create the consumer group (idempotent), starting at new entries."""
        try:
            await self._redis.xgroup_create(self._stream, self._group, id="$", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def run(self, handler: EventHandler) -> None:
        """Consume forever: pending (crash-recovery) first, then new entries.

        A handler failure is logged and the entry acknowledged anyway —
        a poison message must never wedge the whole stream.
        """
        await self.ensure_group()
        await self._drain(handler, from_id="0")  # entries left unacked by a crash
        while True:
            processed = await self._drain(handler, from_id=">")
            if not processed:
                await asyncio.sleep(self._idle_sleep)

    async def _drain(self, handler: EventHandler, from_id: str) -> int:
        try:
            batches = await self._redis.xreadgroup(
                self._group,
                self._consumer,
                {self._stream: from_id},
                count=self._batch,
            )
        except ResponseError as exc:
            # The stream/group may have been trimmed or recreated underneath us.
            logger.warning("stream read failed on %s/%s: %s", self._stream, self._group, exc)
            await asyncio.sleep(1.0)
            return 0
        processed = 0
        # XREADGROUP (no `block=`) always yields the RESP2 shape
        # `[[stream_name, [(id, fields), ...]], ...]` from redis-py; the
        # dict-keyed shapes in its return type are RESP3-only.
        assert batches is None or isinstance(batches, list)
        for _, entries in batches or []:
            for entry_id, fields in entries:
                processed += 1
                payload = _extract_payload(fields) if fields else None
                if payload is not None:
                    try:
                        await handler(payload)
                    except Exception:
                        logger.exception(
                            "handler failed for stream entry %s on %s/%s",
                            entry_id, self._stream, self._group,
                        )
                await self._redis.xack(self._stream, self._group, entry_id)
        return processed


def _extract_payload(fields: dict[Any, Any]) -> dict[str, Any] | None:
    """Decode the JSON 'data' field of a stream entry, tolerating bytes keys."""
    raw = fields.get("data", fields.get(b"data"))
    if raw is None:
        logger.warning("stream entry without 'data' field: %r", fields)
        return None
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("stream entry with unparseable payload")
        return None
    return payload if isinstance(payload, dict) else None
