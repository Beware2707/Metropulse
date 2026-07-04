"""Cache-aside ETA service: the API-facing interface over the ETA engine."""

from __future__ import annotations

import logging

from metropulse.application.eta_engine import EtaEngine
from metropulse.domain.entities import TripContext, VehicleEta, VehiclePosition
from metropulse.infrastructure.redis.eta_cache import RedisEtaCache

logger = logging.getLogger(__name__)


class CachedEtaService:
    """Serves ETAs from Redis when the vehicle hasn't moved, computing on miss.

    Cache failures degrade to computation — an unavailable Redis never breaks
    the ETA path, it only makes it slower.
    """

    def __init__(self, engine: EtaEngine, cache: RedisEtaCache) -> None:
        self._engine = engine
        self._cache = cache

    async def compute(
        self, vehicle: VehiclePosition, context: TripContext
    ) -> VehicleEta | None:
        """ETA for a vehicle, cache-first."""
        try:
            cached = await self._cache.get(vehicle.vehicle_id, vehicle.timestamp)
        except Exception:
            logger.exception("eta cache read failed; computing directly")
            cached = None
        if cached is not None:
            return cached
        eta = await self._engine.compute(vehicle, context)
        if eta is not None:
            try:
                await self._cache.set(vehicle.vehicle_id, vehicle.timestamp, eta)
            except Exception:
                logger.exception("eta cache write failed; serving uncached result")
        return eta
