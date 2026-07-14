"""Park & ride: rank stations that have parking by drive + metro cost.

Given a destination station and the driver's coordinates, this pairs the
curated ``station_facilities`` parking data (capacity/operator/contact per
station) with the journey planner's metro time from each parking station to
the destination. Ranking trades a straight-line drive distance against the
onward metro time.

Honesty notes carried into the API/UI copy:
- ``distance_km`` is a STRAIGHT-LINE distance to the station, not a driving
  distance (we have no road-routing feed).
- Parking capacities are DMRC-published totals, not live availability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.commuter.geo_matching import haversine_meters
from metropulse.application.journey_planner import JourneyPlanner
from metropulse.domain.exceptions import NoRouteError, UnknownEntityError
from metropulse.domain.journey import RideLeg
from metropulse.infrastructure.db.commuter_repositories import (
    StationFacilityRepository,
)
from metropulse.infrastructure.db.repositories import StopRepository

#: Weight on each straight-line kilometre relative to one metro minute when
#: ranking. 2.5 keeps a nearby-but-slower station competitive with a
#: far-but-faster one without letting distance dominate.
_DISTANCE_WEIGHT = 2.5
_MAX_CANDIDATES = 8


@dataclass(frozen=True, slots=True)
class ParkAndRideCandidate:
    """A parking station scored for a drive-then-ride trip."""

    stop_id: str
    name: str
    distance_km: float
    car_capacity: int | None
    motorcycle_capacity: int | None
    cycle_capacity: int | None
    operator: str | None
    contact: str | None
    parking_lat: float | None
    parking_lon: float | None
    metro_minutes: int | None
    metro_summary: str | None


def _summed_capacity(parking_lots: list[dict[str, Any]] | None, key: str) -> int | None:
    """Total capacity across a station's lots for one vehicle type, or None."""
    if not parking_lots:
        return None
    values = [
        value
        for lot in parking_lots
        if isinstance((value := lot.get(key)), int) and not isinstance(value, bool)
    ]
    return sum(values) if values else None


def _first_non_null(parking_lots: list[dict[str, Any]] | None, key: str) -> Any:
    for lot in parking_lots or ():
        value = lot.get(key)
        if value is not None:
            return value
    return None


def _metro_summary(route_long_name: str | None, changes: int) -> str:
    """A short human line like 'Blue Line, 1 change' / 'Red Line, direct'."""
    # route_long_name in this feed is 'RED_Rithala to Dilshad Garden'; take the
    # colour prefix and title-case it into a line name.
    line = "Metro"
    if route_long_name:
        prefix = route_long_name.split("_", 1)[0].strip()
        if prefix:
            line = f"{prefix.title()} Line"
    if changes <= 0:
        return f"{line}, direct"
    return f"{line}, {changes} change{'s' if changes != 1 else ''}"


class ParkAndRideService:
    """Rank parking stations for a drive-then-ride trip to a destination."""

    def __init__(self, planner: JourneyPlanner) -> None:
        self._planner = planner

    async def candidates(
        self, session: AsyncSession, destination: str, lat: float, lon: float
    ) -> list[ParkAndRideCandidate]:
        """Up to eight parking stations, ranked by drive distance + metro time.

        Raises :class:`UnknownEntityError` if the destination stop is unknown.
        Stations with no car or motorcycle capacity are excluded. A station
        the planner can't route to the destination is still returned, ranked
        last (its metro fields are None).
        """
        stops = StopRepository(session)
        if await stops.get(destination) is None:
            raise UnknownEntityError(f"stop '{destination}' not found")

        rows = await StationFacilityRepository(session).all_rows()
        results: list[ParkAndRideCandidate] = []
        for facility in rows:
            car = _summed_capacity(facility.parking_lots, "car")
            motorcycle = _summed_capacity(facility.parking_lots, "motorcycle")
            if not (car or motorcycle):
                continue  # no meaningful parking here
            if facility.stop_id == destination:
                continue  # already at the destination
            station = await stops.get(facility.stop_id)
            if station is None:
                continue
            distance_km = round(
                haversine_meters(lat, lon, station.stop_lat, station.stop_lon) / 1000.0,
                1,
            )
            metro_minutes, metro_summary = await self._metro_leg(
                facility.stop_id, destination
            )
            results.append(
                ParkAndRideCandidate(
                    stop_id=facility.stop_id,
                    name=station.stop_name,
                    distance_km=distance_km,
                    car_capacity=car,
                    motorcycle_capacity=motorcycle,
                    cycle_capacity=_summed_capacity(facility.parking_lots, "cycle"),
                    operator=_first_non_null(facility.parking_lots, "operator"),
                    contact=_first_non_null(facility.parking_lots, "contact"),
                    parking_lat=_first_non_null(facility.parking_lots, "lat"),
                    parking_lon=_first_non_null(facility.parking_lots, "lon"),
                    metro_minutes=metro_minutes,
                    metro_summary=metro_summary,
                )
            )

        results.sort(key=_rank_key)
        return results[:_MAX_CANDIDATES]

    async def _metro_leg(
        self, origin: str, destination: str
    ) -> tuple[int | None, str | None]:
        """(metro minutes, summary) from a parking station to the destination."""
        try:
            plan = await self._planner.plan(origin, destination)
        except (UnknownEntityError, NoRouteError, ValueError):
            return None, None
        minutes = max(1, round(plan.expected_travel_seconds / 60))
        rides = [leg for leg in plan.legs if isinstance(leg, RideLeg)]
        first_line = rides[0].route_long_name if rides else None
        return minutes, _metro_summary(first_line, plan.interchange_count)


def _rank_key(candidate: ParkAndRideCandidate) -> tuple[float, float]:
    """Sort key: distance*weight + metro minutes; unroutable stations last."""
    if candidate.metro_minutes is None:
        return (1.0, candidate.distance_km)  # unroutable: after all routable ones
    return (0.0, candidate.distance_km * _DISTANCE_WEIGHT + candidate.metro_minutes)
