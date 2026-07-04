"""Assembly of presentation-ready train states from raw vehicle positions.

Resolution results are cached in Redis by the worker (one resolve per poll,
network-wide); API reads use the cached state when it matches the vehicle's
current feed timestamp and only recompute on a miss, re-deriving staleness
at read time since it depends on the wall clock.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

from metropulse.application.route_resolver import RouteResolver
from metropulse.domain.entities import TrainState, VehiclePosition, utcnow
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore


class TrainService:
    """Enriches vehicle positions with trip/route/station context."""

    def __init__(
        self,
        store: RedisVehicleStore,
        resolver: RouteResolver,
        stale_after_seconds: float,
    ) -> None:
        self._store = store
        self._resolver = resolver
        self._stale_after = stale_after_seconds

    def _cached_if_fresh(
        self, cached: TrainState | None, vehicle: VehiclePosition, now: datetime
    ) -> TrainState | None:
        """Reuse a cached state only if it was built from this exact position."""
        if cached is None or cached.vehicle.timestamp != vehicle.timestamp:
            return None
        return dataclasses.replace(
            cached, vehicle=vehicle, is_stale=vehicle.is_stale(now, self._stale_after)
        )

    async def assemble(
        self, vehicle: VehiclePosition, now: datetime | None = None
    ) -> TrainState:
        """Build the enriched state for a single vehicle position."""
        now = now or utcnow()
        is_stale = vehicle.is_stale(now, self._stale_after)

        context = None
        if vehicle.trip_id:
            context = await self._resolver.resolve_trip(vehicle.trip_id)

        if context is not None:
            location = self._resolver.locate(vehicle, context)
            return TrainState(
                vehicle=vehicle,
                resolved=True,
                is_stale=is_stale,
                route_id=context.route_id,
                route_short_name=context.route_short_name,
                route_long_name=context.route_long_name,
                route_color=context.route_color,
                headsign=context.headsign,
                direction_id=context.direction_id,
                current_station=location.current_station,
                next_station=location.next_station,
                destination=location.destination,
                at_station=location.at_station,
                distance_along_m=location.distance_along_m,
                shape_offset_m=location.shape_offset_m,
                remaining_stations=location.remaining_stations,
            )

        # Trip unknown: fall back to route-level context so clients can at
        # least label the line the train is on.
        route = None
        if vehicle.route_id:
            route = await self._resolver.resolve_route(vehicle.route_id)
        return TrainState(
            vehicle=vehicle,
            resolved=False,
            is_stale=is_stale,
            route_id=route.route_id if route else None,
            route_short_name=route.route_short_name if route else None,
            route_long_name=route.route_long_name if route else None,
            route_color=route.route_color if route else None,
        )

    async def list_trains(self) -> list[TrainState]:
        """Enriched states for every vehicle, preferring the Redis cache."""
        snapshot = await self._store.get_all()
        cached = await self._store.get_all_train_states()
        now = utcnow()
        states: list[TrainState] = []
        for vehicle_id, vehicle in snapshot.items():
            state = self._cached_if_fresh(cached.get(vehicle_id), vehicle, now)
            if state is None:
                state = await self.assemble(vehicle, now)
            states.append(state)
        states.sort(key=lambda s: s.vehicle.vehicle_id)
        return states

    async def get_train(self, vehicle_id: str) -> TrainState | None:
        """Enriched state for one vehicle (cache-first), or None if unknown."""
        vehicle = await self._store.get(vehicle_id)
        if vehicle is None:
            return None
        now = utcnow()
        cached = self._cached_if_fresh(
            await self._store.get_train_state(vehicle_id), vehicle, now
        )
        if cached is not None:
            return cached
        return await self.assemble(vehicle, now)
