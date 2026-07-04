"""Redis-backed store for the latest vehicle positions.

Layout:
  - ``mp:vehicles``  HASH   vehicle_id -> VehiclePosition JSON
  - ``mp:seq``       STRING monotonically increasing diff sequence
  - ``mp:updates``   PUBSUB channel carrying diff messages for WS fan-out
"""

from __future__ import annotations

import json
from typing import AsyncIterator, Iterable, Mapping

from redis.asyncio import Redis

from metropulse.domain.entities import VehiclePosition

VEHICLES_KEY = "mp:vehicles"
SEQUENCE_KEY = "mp:seq"
UPDATES_CHANNEL = "mp:updates"


class RedisVehicleStore:
    """Latest-position snapshot plus the diff sequence and pub/sub channel."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_all(self) -> dict[str, VehiclePosition]:
        """The full latest-position snapshot keyed by vehicle_id."""
        raw = await self._redis.hgetall(VEHICLES_KEY)
        return {
            _as_str(vehicle_id): VehiclePosition.from_dict(json.loads(_as_str(payload)))
            for vehicle_id, payload in raw.items()
        }

    async def get(self, vehicle_id: str) -> VehiclePosition | None:
        """The latest position for one vehicle, or None."""
        payload = await self._redis.hget(VEHICLES_KEY, vehicle_id)
        if payload is None:
            return None
        return VehiclePosition.from_dict(json.loads(_as_str(payload)))

    async def apply(
        self, upserts: Mapping[str, VehiclePosition], removed_ids: Iterable[str]
    ) -> None:
        """Atomically upsert changed vehicles and delete removed ones."""
        removed = list(removed_ids)
        if not upserts and not removed:
            return
        pipe = self._redis.pipeline(transaction=True)
        if upserts:
            pipe.hset(
                VEHICLES_KEY,
                mapping={vid: json.dumps(pos.to_dict()) for vid, pos in upserts.items()},
            )
        if removed:
            pipe.hdel(VEHICLES_KEY, *removed)
        await pipe.execute()

    async def next_sequence(self) -> int:
        """Increment and return the global diff sequence number."""
        return int(await self._redis.incr(SEQUENCE_KEY))

    async def current_sequence(self) -> int:
        """The current diff sequence number (0 if none published yet)."""
        value = await self._redis.get(SEQUENCE_KEY)
        return int(value) if value is not None else 0

    async def publish_diff(self, message: str) -> None:
        """Publish a serialized diff message to the updates channel."""
        await self._redis.publish(UPDATES_CHANNEL, message)

    async def subscribe_diffs(self) -> AsyncIterator[str]:
        """Yield diff messages as they are published (blocks forever)."""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(UPDATES_CHANNEL)
        try:
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    yield _as_str(message["data"])
        finally:
            await pubsub.unsubscribe(UPDATES_CHANNEL)
            await pubsub.aclose()

    async def ping(self) -> bool:
        """Health-check the Redis connection."""
        return bool(await self._redis.ping())


def _as_str(value: str | bytes) -> str:
    """Redis clients may return bytes or str depending on decode_responses."""
    return value.decode("utf-8") if isinstance(value, bytes) else value
