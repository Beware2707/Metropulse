"""Route resolution: realtime trip IDs -> full static trip context.

Realtime feeds frequently use IDs that don't exactly match the static GTFS
(prefixes, suffixes, different casing). Rather than hardcoding assumptions,
an :class:`IdMapper` generates lookup candidates from configurable sources:

1. the raw ID itself (exact match),
2. an explicit static map (JSON file),
3. regex rewrite rules from configuration.

The first candidate that exists in the static tables wins.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

from metropulse.domain.entities import (
    StationRef,
    StopOnTrip,
    TrainLocation,
    TripContext,
    VehiclePosition,
)
from metropulse.domain.geometry import ShapeGeometry, haversine_m
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.repositories import (
    RouteRepository,
    ShapeRepository,
    TripRepository,
)

logger = logging.getLogger(__name__)

MappingField = Literal["trip_id", "route_id"]


@dataclass(frozen=True, slots=True)
class MappingRule:
    """A regex rewrite applied to a realtime ID to produce a lookup candidate."""

    field: MappingField
    pattern: str
    replacement: str


class IdMapper:
    """Generates ordered, de-duplicated static-ID candidates for a realtime ID."""

    def __init__(
        self,
        rules: Sequence[MappingRule] = (),
        trip_id_map: Mapping[str, str] | None = None,
        route_id_map: Mapping[str, str] | None = None,
    ) -> None:
        self._rules = tuple(rules)
        self._static_maps: dict[MappingField, Mapping[str, str]] = {
            "trip_id": dict(trip_id_map or {}),
            "route_id": dict(route_id_map or {}),
        }
        self._compiled = {rule: re.compile(rule.pattern) for rule in rules}

    def candidates(self, field: MappingField, raw_id: str) -> list[str]:
        """Ordered candidates: exact, explicit map, then regex rewrites."""
        out: list[str] = [raw_id]
        mapped = self._static_maps[field].get(raw_id)
        if mapped is not None:
            out.append(mapped)
        for rule in self._rules:
            if rule.field != field:
                continue
            rewritten = self._compiled[rule].sub(rule.replacement, raw_id)
            if rewritten:
                out.append(rewritten)
        seen: set[str] = set()
        unique: list[str] = []
        for candidate in out:
            if candidate not in seen:
                seen.add(candidate)
                unique.append(candidate)
        return unique


@dataclass(frozen=True, slots=True)
class ResolvedRoute:
    """Route-level fallback when a trip cannot be resolved."""

    route_id: str
    route_short_name: str | None
    route_long_name: str | None
    route_color: str | None


class RouteResolver:
    """Resolves realtime IDs to trip contexts and locates vehicles on them.

    Contexts are cached per realtime trip ID for the process lifetime because
    static GTFS data only changes on redeploy/reload.
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        mapper: IdMapper,
        *,
        station_radius_m: float = 75.0,
    ) -> None:
        self._session_factory = session_factory
        self._mapper = mapper
        self._station_radius_m = station_radius_m
        self._trip_cache: dict[str, TripContext | None] = {}
        self._route_cache: dict[str, ResolvedRoute | None] = {}
        self._lock = asyncio.Lock()

    def clear_cache(self) -> None:
        """Drop cached contexts (call after a static reload)."""
        self._trip_cache.clear()
        self._route_cache.clear()

    async def resolve_trip(self, realtime_trip_id: str) -> TripContext | None:
        """Resolve a realtime trip ID to a full :class:`TripContext`.

        Returns None when no candidate matches a static trip.
        """
        async with self._lock:
            if realtime_trip_id in self._trip_cache:
                return self._trip_cache[realtime_trip_id]
        context = await self._build_context(realtime_trip_id)
        async with self._lock:
            self._trip_cache[realtime_trip_id] = context
        if context is None:
            logger.warning("could not resolve realtime trip_id %r", realtime_trip_id)
        return context

    async def resolve_route(self, realtime_route_id: str) -> ResolvedRoute | None:
        """Route-level fallback resolution for unresolvable trips."""
        async with self._lock:
            if realtime_route_id in self._route_cache:
                return self._route_cache[realtime_route_id]
        resolved: ResolvedRoute | None = None
        async with self._session_factory() as session:
            repo = RouteRepository(session)
            for candidate in self._mapper.candidates("route_id", realtime_route_id):
                route = await repo.get(candidate)
                if route is not None:
                    resolved = ResolvedRoute(
                        route_id=route.route_id,
                        route_short_name=route.route_short_name,
                        route_long_name=route.route_long_name,
                        route_color=route.route_color,
                    )
                    break
        async with self._lock:
            self._route_cache[realtime_route_id] = resolved
        return resolved

    async def _build_context(self, realtime_trip_id: str) -> TripContext | None:
        async with self._session_factory() as session:
            trips = TripRepository(session)
            trip = None
            for candidate in self._mapper.candidates("trip_id", realtime_trip_id):
                trip = await trips.get(candidate)
                if trip is not None:
                    break
            if trip is None:
                return None

            route = await RouteRepository(session).get(trip.route_id)
            pairs = await trips.stop_times_with_stops(trip.trip_id)
            geometry: ShapeGeometry | None = None
            if trip.shape_id:
                points = await ShapeRepository(session).points_for(trip.shape_id)
                if len(points) >= 2:
                    geometry = ShapeGeometry(
                        [(p.shape_pt_lat, p.shape_pt_lon) for p in points]
                    )

            stops = _build_stop_sequence(pairs, geometry)
            return TripContext(
                trip_id=trip.trip_id,
                route_id=trip.route_id,
                route_short_name=route.route_short_name if route else None,
                route_long_name=route.route_long_name if route else None,
                route_color=route.route_color if route else None,
                headsign=trip.trip_headsign,
                direction_id=trip.direction_id,
                shape_id=trip.shape_id,
                stops=stops,
                geometry=geometry,
            )

    def locate(self, vehicle: VehiclePosition, context: TripContext) -> TrainLocation:
        """Determine current/next/destination stations for a vehicle.

        With shape geometry the vehicle is projected onto the polyline; the
        last station at or behind that distance is "current". Without a shape
        we fall back to the nearest stop by great-circle distance.
        """
        destination = _ref(context.stops[-1]) if context.stops else None
        if not context.stops:
            return TrainLocation(None, None, None, False, None, None)

        if context.geometry is not None:
            projection = context.geometry.project(vehicle.latitude, vehicle.longitude)
            distance = projection.distance_along_m
            current, next_stop, at_station = _locate_by_distance(
                context.stops, distance, self._station_radius_m
            )
            return TrainLocation(
                current_station=_ref(current) if current else None,
                next_station=_ref(next_stop) if next_stop else None,
                destination=destination,
                at_station=at_station,
                distance_along_m=distance,
                shape_offset_m=projection.offset_m,
                remaining_stations=_remaining(context.stops, next_stop),
            )

        nearest = min(
            context.stops,
            key=lambda s: haversine_m(vehicle.latitude, vehicle.longitude,
                                      s.latitude, s.longitude),
        )
        gap = haversine_m(vehicle.latitude, vehicle.longitude, nearest.latitude, nearest.longitude)
        index = context.stops.index(nearest)
        next_stop = context.stops[index + 1] if index + 1 < len(context.stops) else None
        return TrainLocation(
            current_station=_ref(nearest),
            next_station=_ref(next_stop) if next_stop else None,
            destination=destination,
            at_station=gap <= self._station_radius_m,
            distance_along_m=nearest.distance_along_shape_m,
            shape_offset_m=None,
            remaining_stations=_remaining(context.stops, next_stop),
        )


def _locate_by_distance(
    stops: tuple[StopOnTrip, ...], distance_m: float, radius_m: float
) -> tuple[StopOnTrip | None, StopOnTrip | None, bool]:
    """(current, next, at_station) given a distance along the shape."""
    for i, stop in enumerate(stops):
        if abs(stop.distance_along_shape_m - distance_m) <= radius_m:
            next_stop = stops[i + 1] if i + 1 < len(stops) else None
            return stop, next_stop, True
    current: StopOnTrip | None = None
    next_stop = None
    for i, stop in enumerate(stops):
        if stop.distance_along_shape_m <= distance_m:
            current = stop
        else:
            next_stop = stop
            break
    return current, next_stop, False


def _build_stop_sequence(
    pairs: Sequence[tuple[object, object]], geometry: ShapeGeometry | None
) -> tuple[StopOnTrip, ...]:
    """Build the ordered stop sequence with distances along the trip.

    Distances come from projecting each stop onto the shape, constrained to be
    monotonically non-decreasing so out-and-back shapes cannot fold the
    sequence back on itself. Without a shape, cumulative straight-line
    distances between consecutive stops are used.
    """
    stops: list[StopOnTrip] = []
    floor = 0.0
    prev_lat: float | None = None
    prev_lon: float | None = None
    for stop_time, stop in pairs:  # type: ignore[assignment]
        lat = stop.stop_lat  # type: ignore[attr-defined]
        lon = stop.stop_lon  # type: ignore[attr-defined]
        if geometry is not None:
            projection = geometry.project(lat, lon, min_distance_m=floor)
            distance = projection.distance_along_m
        elif prev_lat is not None and prev_lon is not None:
            distance = floor + haversine_m(prev_lat, prev_lon, lat, lon)
        else:
            distance = 0.0
        stops.append(
            StopOnTrip(
                stop_id=stop.stop_id,  # type: ignore[attr-defined]
                stop_name=stop.stop_name,  # type: ignore[attr-defined]
                sequence=stop_time.stop_sequence,  # type: ignore[attr-defined]
                latitude=lat,
                longitude=lon,
                arrival_seconds=stop_time.arrival_seconds,  # type: ignore[attr-defined]
                departure_seconds=stop_time.departure_seconds,  # type: ignore[attr-defined]
                distance_along_shape_m=distance,
            )
        )
        floor = distance
        prev_lat, prev_lon = lat, lon
    return tuple(stops)


def _ref(stop: StopOnTrip) -> StationRef:
    return StationRef(stop_id=stop.stop_id, name=stop.stop_name, sequence=stop.sequence)


def _remaining(
    stops: tuple[StopOnTrip, ...], next_stop: StopOnTrip | None
) -> tuple[StationRef, ...]:
    """All stations still ahead, starting from the next one."""
    if next_stop is None:
        return ()
    index = stops.index(next_stop)
    return tuple(_ref(stop) for stop in stops[index:])
