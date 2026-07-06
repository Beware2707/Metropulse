"""Tests for schedule-based vehicle position estimation.

Covers three things independently: the repository query for trips currently
underway, the pure interpolation function (including the dwell-at-a-station
gap a naive segment-only interpolation would miss), and the end-to-end
estimator cycle against the fixture GTFS dataset.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from metropulse.application.commuter.last_train import LastTrainService
from metropulse.application.route_resolver import RouteResolver
from metropulse.application.schedule_position_source import (
    ScheduleEstimatedPositionSource,
    _interpolate,
)
from metropulse.domain.entities import StopOnTrip, TripContext
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.repositories import TripRepository

IST = ZoneInfo("Asia/Kolkata")

# calendar.txt's "WK" service runs every day of the week in this range, so
# any date here is active regardless of weekday -- except the explicit
# calendar_dates.txt exception on 2026-08-15.
_ACTIVE_DATE = datetime(2026, 1, 5, tzinfo=IST)
_EXCLUDED_DATE = datetime(2026, 8, 15, tzinfo=IST)


# --- TripRepository.active_trip_ids_at ------------------------------------------------


async def test_active_trip_ids_at_returns_trip_underway(
    loaded_session_factory: SessionFactory,
) -> None:
    async with loaded_session_factory() as session:
        # T1: S1 dep 08:00:30 (28830s) .. S4 arr 08:09:00 (29340s).
        trip_ids = await TripRepository(session).active_trip_ids_at(["WK"], 29000)
    assert "T1" in trip_ids
    assert "T2" not in trip_ids  # T2 runs 09:00-09:09, not yet underway


async def test_active_trip_ids_at_empty_outside_service_hours(
    loaded_session_factory: SessionFactory,
) -> None:
    async with loaded_session_factory() as session:
        trip_ids = await TripRepository(session).active_trip_ids_at(["WK"], 1000)
    assert list(trip_ids) == []


async def test_active_trip_ids_at_empty_for_no_service_ids(
    loaded_session_factory: SessionFactory,
) -> None:
    async with loaded_session_factory() as session:
        trip_ids = await TripRepository(session).active_trip_ids_at([], 29000)
    assert list(trip_ids) == []


# --- _interpolate ----------------------------------------------------------------------


async def test_interpolate_before_first_departure_sits_at_first_stop(
    resolver: RouteResolver,
) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    point = _interpolate(context, 100)
    assert point == (context.stops[0].latitude, context.stops[0].longitude)


async def test_interpolate_after_last_arrival_sits_at_last_stop(
    resolver: RouteResolver,
) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    point = _interpolate(context, 50_000)
    assert point == (context.stops[-1].latitude, context.stops[-1].longitude)


async def test_interpolate_during_dwell_sits_at_that_stop(
    resolver: RouteResolver,
) -> None:
    """Regression test: a naive "only interpolate between consecutive stops'
    departure/arrival" implementation leaves the dwell window (a stop's own
    arrival to its own departure) uncovered, making the train vanish from
    the map for the ~30s it sits at every intermediate station."""
    context = await resolver.resolve_trip("T1")
    assert context is not None
    s2 = context.stops[1]
    assert s2.arrival_seconds < s2.departure_seconds  # a real dwell window exists
    midway_through_dwell = (s2.arrival_seconds + s2.departure_seconds) // 2
    point = _interpolate(context, midway_through_dwell)
    assert point == (s2.latitude, s2.longitude)


async def test_interpolate_midpoint_between_stops(resolver: RouteResolver) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    s2, s3 = context.stops[1], context.stops[2]
    elapsed = (s2.departure_seconds + s3.arrival_seconds) // 2
    point = _interpolate(context, elapsed)
    assert point is not None
    expected_distance = (s2.distance_along_shape_m + s3.distance_along_shape_m) / 2
    assert context.geometry is not None
    expected = context.geometry.point_at(expected_distance)
    assert point[0] == pytest.approx(expected[0], abs=1e-6)
    assert point[1] == pytest.approx(expected[1], abs=1e-6)


def test_interpolate_returns_none_without_shape_geometry() -> None:
    stop = StopOnTrip(
        stop_id="S1", stop_name="Alpha", sequence=1,
        latitude=28.60, longitude=77.00,
        arrival_seconds=100, departure_seconds=100,
        distance_along_shape_m=0.0,
    )
    context = TripContext(
        trip_id="T1", route_id="R1", route_short_name=None, route_long_name=None,
        route_color=None, headsign=None, direction_id=None, shape_id=None,
        stops=(stop,), geometry=None,
    )
    assert _interpolate(context, 500) is None


# --- ScheduleEstimatedPositionSource ------------------------------------------------------


async def test_fetch_positions_estimates_a_trip_in_progress(
    loaded_session_factory: SessionFactory,
    resolver: RouteResolver,
) -> None:
    last_train = LastTrainService(timezone="Asia/Kolkata")
    source = ScheduleEstimatedPositionSource(loaded_session_factory, last_train, resolver)

    # 08:04:45 local -- between S2 (dep 08:03:30) and S3 (arr 08:06:00).
    now = _ACTIVE_DATE.replace(hour=8, minute=4, second=45)
    positions = await source.fetch_positions(now)

    assert len(positions) == 1
    position = positions[0]
    assert position.vehicle_id == "sched-T1"
    assert position.trip_id == "T1"
    assert position.route_id == "R1"
    assert position.source == "schedule_estimate"
    assert position.timestamp == now
    # Somewhere between S2 (77.01) and S3 (77.02), not exactly at either.
    assert 77.01 < position.longitude < 77.02


async def test_fetch_positions_empty_when_no_trip_is_running(
    loaded_session_factory: SessionFactory,
    resolver: RouteResolver,
) -> None:
    last_train = LastTrainService(timezone="Asia/Kolkata")
    source = ScheduleEstimatedPositionSource(loaded_session_factory, last_train, resolver)

    now = _ACTIVE_DATE.replace(hour=2, minute=0, second=0)
    assert await source.fetch_positions(now) == []


async def test_fetch_positions_empty_on_a_calendar_exception_date(
    loaded_session_factory: SessionFactory,
    resolver: RouteResolver,
) -> None:
    """2026-08-15 is a calendar_dates.txt exception removing service "WK" --
    T1 would otherwise be running at this time of day."""
    last_train = LastTrainService(timezone="Asia/Kolkata")
    source = ScheduleEstimatedPositionSource(loaded_session_factory, last_train, resolver)

    now = _EXCLUDED_DATE.replace(hour=8, minute=4, second=45)
    assert await source.fetch_positions(now) == []
