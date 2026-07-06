"""Redis-backed store for the latest vehicle positions and resolved states.

Layout:
  - ``mp:vehicles``  HASH   vehicle_id -> VehiclePosition JSON
  - ``mp:trains``    HASH   vehicle_id -> resolved TrainState JSON (worker-written)
  - ``mp:seq``       STRING monotonically increasing diff sequence
  - ``mp:updates``   STREAM diff/alert events (durable; consumer groups for
                     notify/ETA/analytics, plain reads for WS gateways)

The worker is the single writer of ``mp:trains``: it resolves every changed
vehicle once per poll and caches the result, so API replicas serve resolution
(route, direction, stations, line colour) without recomputing it per request.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, AsyncIterator, Iterable, Mapping

from redis.asyncio import Redis

from metropulse.domain.entities import TrainState, VehiclePosition

VEHICLES_KEY = "mp:vehicles"
TRAINS_KEY = "mp:trains"
SEQUENCE_KEY = "mp:seq"
FEED_SUCCESS_KEY = "mp:feed:last_success"
UPDATES_STREAM = "mp:updates"
# Bounds stream memory (~a few MB at DMRC scale) while giving consumers and
# reconnecting gateways minutes of replayable history.
STREAM_MAXLEN = 4096


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
            pipe.hdel(TRAINS_KEY, *removed)
        await pipe.execute()

    async def cache_train_states(
        self, states: Mapping[str, dict[str, Any]], removed_ids: Iterable[str] = ()
    ) -> None:
        """Cache resolved train states (worker-side, once per poll)."""
        removed = list(removed_ids)
        if not states and not removed:
            return
        pipe = self._redis.pipeline(transaction=True)
        if states:
            pipe.hset(
                TRAINS_KEY,
                mapping={vid: json.dumps(state) for vid, state in states.items()},
            )
        if removed:
            pipe.hdel(TRAINS_KEY, *removed)
        await pipe.execute()

    async def get_train_state(self, vehicle_id: str) -> TrainState | None:
        """One cached resolved train state, or None."""
        payload = await self._redis.hget(TRAINS_KEY, vehicle_id)
        if payload is None:
            return None
        return TrainState.from_dict(json.loads(_as_str(payload)))

    async def get_all_train_states(self) -> dict[str, TrainState]:
        """All cached resolved train states keyed by vehicle id."""
        raw = await self._redis.hgetall(TRAINS_KEY)
        return {
            _as_str(vehicle_id): TrainState.from_dict(json.loads(_as_str(payload)))
            for vehicle_id, payload in raw.items()
        }

    async def next_sequence(self) -> int:
        """Increment and return the global diff sequence number."""
        return int(await self._redis.incr(SEQUENCE_KEY))

    async def current_sequence(self) -> int:
        """The current diff sequence number (0 if none published yet)."""
        value = await self._redis.get(SEQUENCE_KEY)
        return int(value) if value is not None else 0

    async def publish_diff(self, message: str) -> None:
        """Append a serialized diff/alert event to the durable updates stream."""
        await self._redis.xadd(
            UPDATES_STREAM, {"data": message}, maxlen=STREAM_MAXLEN, approximate=True
        )

    async def subscribe_diffs(self) -> AsyncIterator[str]:
        """Yield update events as they are appended to the stream (forever).

        Fan-out reads for WebSocket gateways: each caller tracks its own
        stream position starting from "now", so every API replica sees every
        event without consumer-group coordination. Short non-blocking polls
        keep cancellation prompt and work identically on fakeredis.
        """
        last_id = await self._latest_stream_id()
        while True:
            batches = await self._redis.xread({UPDATES_STREAM: last_id}, count=64)
            if not batches:
                await asyncio.sleep(0.1)
                continue
            # Non-blocking XREAD (no `block=`) always yields the RESP2 shape
            # `[[stream_name, [(id, fields), ...]], ...]` from redis-py; the
            # dict-keyed shapes in its return type are RESP3-only.
            assert isinstance(batches, list)
            for _, entries in batches:
                for entry_id, fields in entries:
                    last_id = _as_str(entry_id)
                    data = fields.get("data", fields.get(b"data")) if fields else None
                    if data is not None:
                        yield _as_str(data)

    async def _latest_stream_id(self) -> str:
        """The current tail of the updates stream ('0-0' when empty)."""
        entries = await self._redis.xrevrange(UPDATES_STREAM, count=1)
        if not entries:
            return "0-0"
        entry_id = entries[0][0]
        assert entry_id is not None
        return _as_str(entry_id)

    async def vehicle_count(self) -> int:
        """Number of vehicles in the latest snapshot (O(1) HLEN)."""
        return int(await self._redis.hlen(VEHICLES_KEY))

    async def record_feed_success(self, at: datetime) -> None:
        """Record the moment of the last successful feed poll (health probe)."""
        await self._redis.set(FEED_SUCCESS_KEY, at.isoformat())

    async def feed_age_seconds(self, now: datetime) -> float | None:
        """Seconds since the last successful poll, or None if never polled."""
        raw = await self._redis.get(FEED_SUCCESS_KEY)
        if raw is None:
            return None
        return (now - datetime.fromisoformat(_as_str(raw))).total_seconds()

    async def ping(self) -> bool:
        """Health-check the Redis connection."""
        return bool(await self._redis.ping())


def _as_str(value: str | bytes) -> str:
    """Redis clients may return bytes or str depending on decode_responses."""
    return value.decode("utf-8") if isinstance(value, bytes) else value
