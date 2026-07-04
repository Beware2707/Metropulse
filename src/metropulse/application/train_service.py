"""Assembly of presentation-ready train states from raw vehicle positions."""

from __future__ import annotations

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
        """Enriched states for every vehicle in the latest snapshot."""
        snapshot = await self._store.get_all()
        now = utcnow()
        states = [await self.assemble(vehicle, now) for vehicle in snapshot.values()]
        states.sort(key=lambda s: s.vehicle.vehicle_id)
        return states

    async def get_train(self, vehicle_id: str) -> TrainState | None:
        """Enriched state for one vehicle, or None if unknown."""
        vehicle = await self._store.get(vehicle_id)
        if vehicle is None:
            return None
        return await self.assemble(vehicle)
