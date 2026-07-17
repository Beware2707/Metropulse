"""Commute Replay: turns a completed trip (or a month of them) into the
story a commuter actually cares about — time saved, money saved, CO2 saved —
instead of a bare row in a history table.

Every figure here is a documented estimate, never a live pricing/traffic
API MetroPulse doesn't have:

- ``distance_km`` is the real straight-line distance between the origin and
  destination stations (haversine) — an honest lower bound on the actual
  route distance, not a guess.
- ``metro_fare_rupees`` reuses the exact same fare-slab estimator the
  Flutter client already shows elsewhere (``app/lib/domain/fare.dart``),
  ported here so the two never disagree.
- ``estimated_cab_fare_rupees`` and the road-time/CO2 figures use named,
  adjustable constants below — realistic Delhi averages, not arbitrary
  numbers, and always presented to the user as an estimate.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.domain.exceptions import UnknownEntityError
from metropulse.domain.geometry import haversine_m
from metropulse.domain.replay import MonthlyReplay, TripReplay
from metropulse.infrastructure.db.commuter_models import Journey
from metropulse.infrastructure.db.commuter_repositories import JourneyRepository
from metropulse.infrastructure.db.repositories import StopRepository

# Same assumption Flutter's estimateFare() uses, so the two never disagree:
# DMRC publishes no fare API, so both derive distance from the assumed
# average commercial speed (line-haul + dwell) rather than an exact figure.
_ASSUMED_METRO_SPEED_KMH = 33.0

# DMRC smart-card fare slabs (rupees), upper-bound-inclusive, ascending —
# mirrors app/lib/domain/fare.dart exactly.
_FARE_SLABS: tuple[tuple[float, int], ...] = (
    (2.0, 10),
    (5.0, 20),
    (12.0, 30),
    (21.0, 40),
    (32.0, 50),
)
_FARE_BEYOND_LAST_SLAB = 60

# Typical Delhi peak-hour road speed for a private car/cab (widely-cited
# range is roughly 15-20 km/h); 18 km/h is a reasonable midpoint.
_ASSUMED_ROAD_SPEED_KMH = 18.0

# A standard app-cab's base fare + per-km rate in Delhi — illustrative, not
# a live pricing feed.
_CAB_BASE_FARE_RUPEES = 40
_CAB_PER_KM_RUPEES = 16.0

# Typical grams-CO2-per-km: an average private car versus Delhi Metro's
# per-passenger footprint (metro is electric and carries far more people
# per vehicle). Commonly-cited illustrative averages, not measured values.
_CAR_CO2_KG_PER_KM = 0.12
_METRO_CO2_KG_PER_KM = 0.03


class CommuteImpactService:
    """Builds trip/monthly replays from a user's completed journey history."""

    def __init__(self, *, monthly_window_days: float = 30.0) -> None:
        self._monthly_window = timedelta(days=monthly_window_days)

    async def latest_trip(self, session: AsyncSession, user_id: str) -> TripReplay:
        """The user's most recently completed trip, replayed.

        Raises :class:`UnknownEntityError` if the user has no completed
        journeys yet.
        """
        journey = await JourneyRepository(session).latest_completed_for_user(user_id)
        if journey is None:
            raise UnknownEntityError("no completed journeys yet to replay")
        replays = await self._replay_many(session, [journey])
        if replays[0] is None:
            raise UnknownEntityError("the stations on that journey no longer exist")
        return replays[0]

    async def monthly_summary(
        self, session: AsyncSession, user_id: str, now: datetime
    ) -> MonthlyReplay:
        """A rolling-window summary of the user's completed trips.

        Never raises: zero trips is a valid (empty) summary, not an error.
        """
        since = now - self._monthly_window
        journeys = await JourneyRepository(session).completed_since_for_user(user_id, since)
        replays = [r for r in await self._replay_many(session, journeys) if r is not None]

        return MonthlyReplay(
            period_start=since,
            period_end=now,
            trip_count=len(replays),
            total_distance_km=round(sum(r.distance_km for r in replays), 1),
            total_time_saved_seconds=sum(r.time_saved_seconds for r in replays),
            total_money_saved_rupees=sum(r.money_saved_rupees for r in replays),
            total_co2_saved_kg=round(sum(r.co2_saved_kg for r in replays), 1),
        )

    async def _replay_many(
        self, session: AsyncSession, journeys: Sequence[Journey]
    ) -> list[TripReplay | None]:
        stops = StopRepository(session)
        cache: dict[str, tuple[float, float, str] | None] = {}

        async def stop_info(stop_id: str) -> tuple[float, float, str] | None:
            if stop_id not in cache:
                stop = await stops.get(stop_id)
                cache[stop_id] = (
                    None if stop is None else (stop.stop_lat, stop.stop_lon, stop.stop_name)
                )
            return cache[stop_id]

        results: list[TripReplay | None] = []
        for journey in journeys:
            origin = await stop_info(journey.origin_stop_id)
            destination = await stop_info(journey.destination_stop_id)
            results.append(_build_replay(journey, origin, destination))
        return results


def _build_replay(
    journey: Journey,
    origin: tuple[float, float, str] | None,
    destination: tuple[float, float, str] | None,
) -> TripReplay | None:
    if origin is None or destination is None or journey.ended_at is None:
        return None
    olat, olon, oname = origin
    dlat, dlon, dname = destination
    distance_km = haversine_m(olat, olon, dlat, dlon) / 1000.0

    duration_seconds = max(0.0, (journey.ended_at - journey.started_at).total_seconds())

    metro_fare = _slab_fare(distance_km)
    cab_fare = round(_CAB_BASE_FARE_RUPEES + _CAB_PER_KM_RUPEES * distance_km)
    money_saved = max(0, cab_fare - metro_fare)

    road_time_seconds = distance_km / _ASSUMED_ROAD_SPEED_KMH * 3600.0
    time_saved = max(0.0, road_time_seconds - duration_seconds)

    co2_saved = max(0.0, distance_km * (_CAR_CO2_KG_PER_KM - _METRO_CO2_KG_PER_KM))

    return TripReplay(
        origin_stop_id=journey.origin_stop_id,
        origin_name=oname,
        destination_stop_id=journey.destination_stop_id,
        destination_name=dname,
        started_at=journey.started_at,
        ended_at=journey.ended_at,
        duration_seconds=duration_seconds,
        distance_km=round(distance_km, 1),
        metro_fare_rupees=metro_fare,
        estimated_cab_fare_rupees=cab_fare,
        money_saved_rupees=money_saved,
        time_saved_seconds=time_saved,
        co2_saved_kg=round(co2_saved, 2),
    )


def _slab_fare(distance_km: float) -> int:
    for max_km, rupees in _FARE_SLABS:
        if distance_km <= max_km:
            return rupees
    return _FARE_BEYOND_LAST_SLAB
