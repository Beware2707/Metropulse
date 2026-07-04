"""Redis cache for computed ETAs.

Entries are keyed by vehicle and validated against the vehicle position's
feed timestamp: a cached ETA is only served while the vehicle hasn't moved
(same feed sample). A short TTL bounds staleness even for parked vehicles.
"""

from __future__ import annotations

import json
from datetime import datetime

from redis.asyncio import Redis

from metropulse.domain.entities import VehicleEta

_KEY = "mp:eta:{vehicle_id}"


class RedisEtaCache:
    """Timestamp-validated, TTL-bounded ETA cache."""

    def __init__(self, redis: Redis, ttl_seconds: float = 30.0) -> None:
        self._redis = redis
        self._ttl = max(int(ttl_seconds), 1)

    async def get(self, vehicle_id: str, vehicle_timestamp: datetime) -> VehicleEta | None:
        """Cached ETA for this exact vehicle position, or None."""
        raw = await self._redis.get(_KEY.format(vehicle_id=vehicle_id))
        if raw is None:
            return None
        payload = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
        if payload.get("vehicle_ts") != vehicle_timestamp.isoformat():
            return None
        return VehicleEta.from_dict(payload["eta"])

    async def set(
        self, vehicle_id: str, vehicle_timestamp: datetime, eta: VehicleEta
    ) -> None:
        """Store an ETA for this vehicle position."""
        payload = json.dumps(
            {"vehicle_ts": vehicle_timestamp.isoformat(), "eta": eta.to_dict()}
        )
        await self._redis.set(_KEY.format(vehicle_id=vehicle_id), payload, ex=self._ttl)
