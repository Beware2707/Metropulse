"""Schedule-based vehicle position estimation -- Metro Intelligence.

The honest fallback when no licensed realtime vehicle feed is configured
(see ``config.Settings.gtfs_rt_enabled`` and ``cli.run_worker``): rather than
show nothing, or worse, mislabel someone else's data as live metro GPS, this
interpolates each currently-underway trip's position along its shape from
the static timetable alone, and tags every result ``source="schedule_estimate"``
(see ``domain.entities.VehiclePosition``) so nothing downstream can mistake
it for real telemetry.
"""

from __future__ import annotations

import logging
from datetime import datetime, time

from metropulse.application.commuter.last_train import LastTrainService
from metropulse.application.route_resolver import RouteResolver
from metropulse.domain.entities import TripContext, VehiclePosition, utcnow
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.repositories import TripRepository

logger = logging.getLogger(__name__)


class ScheduleEstimatedPositionSource:
    """Estimates current vehicle positions from the GTFS static timetable.

    Implements the same seam as a real feed
    (:class:`~metropulse.application.realtime_engine.PositionSource`), so
    :class:`~metropulse.application.realtime_engine.RealtimeEngine` treats
    it identically to a real one -- the entire existing pipeline
    (diff/store/publish/history/ETA/route-resolution) applies unchanged.
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        last_train: LastTrainService,
        resolver: RouteResolver,
    ) -> None:
        self._session_factory = session_factory
        self._last_train = last_train
        self._resolver = resolver

    async def fetch_positions(self, now: datetime | None = None) -> list[VehiclePosition]:
        """One estimation cycle: a position for every trip underway right now.

        ``now`` is injectable for deterministic tests; defaults to the
        actual current time in production.
        """
        now = now or utcnow()
        local_now = now.astimezone(self._last_train.tz)
        service_date = local_now.date()
        midnight = datetime.combine(service_date, time(0), tzinfo=self._last_train.tz)
        elapsed_seconds = int((local_now - midnight).total_seconds())

        async with self._session_factory() as session:
            active_service_ids = await self._last_train.active_service_ids(session, service_date)
            if not active_service_ids:
                return []
            trip_ids = await TripRepository(session).active_trip_ids_at(
                list(active_service_ids), elapsed_seconds
            )

        positions: list[VehiclePosition] = []
        for trip_id in trip_ids:
            context = await self._resolver.resolve_trip(trip_id)
            if context is None:
                continue
            point = _interpolate(context, elapsed_seconds)
            if point is None:
                continue
            latitude, longitude = point
            positions.append(
                VehiclePosition(
                    vehicle_id=f"sched-{trip_id}",
                    latitude=latitude,
                    longitude=longitude,
                    timestamp=now,
                    trip_id=context.trip_id,
                    route_id=context.route_id,
                    source="schedule_estimate",
                )
            )
        return positions


def _interpolate(context: TripContext, elapsed_seconds: int) -> tuple[float, float] | None:
    """The (lat, lon) a trip's vehicle would be at, this far into the service day.

    Requires shape geometry -- without it there's no honest way to place a
    point between two stops, so a trip missing one is simply skipped
    (rare: DMRC's static feed supplies a shape for every trip).

    Covers the full timeline with no gaps: before the first departure (at
    the first stop), during an intermediate stop's dwell between its own
    arrival and departure (at that stop -- travel-segment interpolation
    alone leaves this window uncovered), between two stops (interpolated
    along the shape), and at or after the last arrival (at the last stop).
    """
    stops = context.stops
    if not stops or context.geometry is None:
        return None
    if elapsed_seconds <= stops[0].departure_seconds:
        return stops[0].latitude, stops[0].longitude
    if elapsed_seconds >= stops[-1].arrival_seconds:
        return stops[-1].latitude, stops[-1].longitude
    for stop in stops[1:-1]:
        if stop.arrival_seconds <= elapsed_seconds <= stop.departure_seconds:
            return stop.latitude, stop.longitude
    for prev_stop, next_stop in zip(stops, stops[1:]):
        if prev_stop.departure_seconds <= elapsed_seconds <= next_stop.arrival_seconds:
            span = next_stop.arrival_seconds - prev_stop.departure_seconds
            fraction = (
                0.0
                if span <= 0
                else (elapsed_seconds - prev_stop.departure_seconds) / span
            )
            fraction = min(max(fraction, 0.0), 1.0)
            distance = prev_stop.distance_along_shape_m + fraction * (
                next_stop.distance_along_shape_m - prev_stop.distance_along_shape_m
            )
            return context.geometry.point_at(distance)
    return None
