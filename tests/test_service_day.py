"""Timetable coverage: telling "no trains" apart from "no data".

The bug this guards against is live in the shipped feed. DMRC's GTFS declares
a ``sunday`` service in calendar.txt and attaches ZERO trips to it (5,379
weekday, 59 Saturday, 0 Sunday). Every Sunday the arrivals board is therefore
empty and the app said "No trains headed this way right now" — which a rider
reads as *the metro is not running*. It is running; we are blind.

The trap is that the obvious check passes: ``active_service_ids`` reads the
calendar, and on a Sunday it returns ``{"sunday"}``. Non-empty. Only counting
the trips attached to those services tells the truth.
"""

from __future__ import annotations

from datetime import date

import httpx

from metropulse.application.commuter.last_train import LastTrainService
from metropulse.application.commuter.service_day import ServiceDayService
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.models import Calendar, Trip


def _service() -> ServiceDayService:
    return ServiceDayService(LastTrainService(timezone="Asia/Kolkata"))


async def test_a_day_with_trips_reports_a_timetable(
    loaded_session_factory: SessionFactory,
) -> None:
    async with loaded_session_factory() as session:
        trip = (await session.execute(__import__("sqlalchemy").select(Trip))).scalars().first()
        assert trip is not None, "fixture must have trips, or this proves nothing"
        calendar = await session.get(Calendar, trip.service_id)
        assert calendar is not None
        # A date the fixture's own calendar covers.
        on = calendar.start_date
        for _ in range(7):
            coverage = await _service().coverage(session, on)
            if coverage.has_timetable:
                assert coverage.scheduled_trips > 0
                return
            on = date.fromordinal(on.toordinal() + 1)
    raise AssertionError("no day in the fixture week has any scheduled trips")


async def test_a_calendar_entry_with_no_trips_is_not_a_timetable(
    loaded_session_factory: SessionFactory,
) -> None:
    """The exact shape of the real Sunday bug, reproduced.

    A service the calendar says runs every day, that no trip references. The
    naive check ("are any services active?") says yes; the honest one says we
    have nothing to show.
    """
    async with loaded_session_factory() as session:
        async with session.begin():
            session.add(
                Calendar(
                    service_id="ghost_service",
                    monday=True, tuesday=True, wednesday=True, thursday=True,
                    friday=True, saturday=True, sunday=True,
                    start_date=date(2030, 1, 1),
                    end_date=date(2030, 12, 31),
                )
            )

    async with loaded_session_factory() as session:
        on = date(2030, 6, 2)
        active = await LastTrainService(timezone="Asia/Kolkata").active_service_ids(
            session, on
        )
        assert "ghost_service" in active, (
            "the calendar must consider it active — that is what makes this a trap"
        )

        coverage = await _service().coverage(session, on)
        assert coverage.active_service_ids  # non-empty, and still...
        assert coverage.scheduled_trips == 0
        assert coverage.has_timetable is False, (
            "a calendar row no trip uses is not a timetable"
        )


async def test_a_date_outside_every_calendar_has_no_timetable(
    loaded_session_factory: SessionFactory,
) -> None:
    async with loaded_session_factory() as session:
        coverage = await _service().coverage(session, date(1999, 1, 1))
    assert coverage.active_service_ids == ()
    assert coverage.scheduled_trips == 0
    assert coverage.has_timetable is False


async def test_service_day_endpoint_reports_coverage(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/service-day", params={"on": "1999-01-01"})
    assert response.status_code == 200
    body = response.json()
    assert body["service_date"] == "1999-01-01"
    assert body["has_timetable"] is False
    assert body["scheduled_trips"] == 0

    today = await api_client.get("/api/v1/service-day")
    assert today.status_code == 200
    # Whatever today is, the shape must be answerable without a date argument —
    # the client calls it exactly this way.
    assert set(today.json()) == {
        "service_date", "has_timetable", "scheduled_trips", "active_service_ids",
    }
