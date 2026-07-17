"""Last-train computation from static GTFS and reminder evaluation.

GTFS service calendars (calendar + calendar_dates exceptions) decide which
trips run on a date; the last *boardable* departure excludes a trip's terminal
stop (you cannot board a train at its final station). Departures past
midnight (>24:00:00) resolve to a datetime on the following civil day while
still belonging to the earlier service date — reminder evaluation therefore
also considers yesterday's service in the small hours.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import func

from metropulse.domain.commuter import LastTrainInfo
from metropulse.infrastructure.db.commuter_models import LastTrainReminder
from metropulse.infrastructure.db.commuter_repositories import LastTrainReminderRepository
from metropulse.infrastructure.db.models import Calendar, CalendarDate, StopTime, Trip

_WEEKDAY_FLAGS = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)


class LastTrainService:
    """Last-departure lookups and last-train reminder evaluation."""

    def __init__(self, timezone: str = "Asia/Kolkata") -> None:
        self._tz = ZoneInfo(timezone)

    @property
    def tz(self) -> ZoneInfo:
        """The network's local timezone."""
        return self._tz

    async def active_service_ids(self, session: AsyncSession, on: date) -> set[str]:
        """Service IDs running on a date (calendar plus exceptions)."""
        calendars = (await session.execute(select(Calendar))).scalars().all()
        weekday_flag = _WEEKDAY_FLAGS[on.weekday()]
        active = {
            c.service_id
            for c in calendars
            if c.start_date <= on <= c.end_date and getattr(c, weekday_flag)
        }
        exceptions = (
            (await session.execute(select(CalendarDate).where(CalendarDate.date == on)))
            .scalars()
            .all()
        )
        for exception in exceptions:
            if exception.exception_type == 1:
                active.add(exception.service_id)
            elif exception.exception_type == 2:
                active.discard(exception.service_id)
        return active

    async def last_departure(
        self,
        session: AsyncSession,
        stop_id: str,
        service_date: date,
        route_id: str | None = None,
        direction_id: int | None = None,
    ) -> LastTrainInfo | None:
        """The last boardable departure from a stop on a service date."""
        active = await self.active_service_ids(session, service_date)
        if not active:
            return None
        terminal_stop_time = aliased(StopTime)
        terminal_seq = (
            select(func.max(terminal_stop_time.stop_sequence))
            .where(terminal_stop_time.trip_id == StopTime.trip_id)
            .scalar_subquery()
        )
        stmt = (
            select(StopTime, Trip)
            .join(Trip, Trip.trip_id == StopTime.trip_id)
            .where(
                StopTime.stop_id == stop_id,
                Trip.service_id.in_(active),
                StopTime.stop_sequence < terminal_seq,
            )
        )
        if route_id is not None:
            stmt = stmt.where(Trip.route_id == route_id)
        if direction_id is not None:
            stmt = stmt.where(Trip.direction_id == direction_id)
        stmt = stmt.order_by(StopTime.departure_seconds.desc()).limit(1)
        row = (await session.execute(stmt)).first()
        if row is None:
            return None
        stop_time, trip = row[0], row[1]
        midnight = datetime.combine(service_date, time(0), tzinfo=self._tz)
        return LastTrainInfo(
            stop_id=stop_id,
            route_id=trip.route_id,
            trip_id=trip.trip_id,
            direction_id=trip.direction_id,
            headsign=trip.trip_headsign,
            service_date=service_date,
            departure_seconds=stop_time.departure_seconds,
            departure_at=midnight + timedelta(seconds=stop_time.departure_seconds),
        )

    async def next_departure(
        self,
        session: AsyncSession,
        stop_id: str,
        after: datetime,
        route_id: str | None = None,
        direction_id: int | None = None,
    ) -> LastTrainInfo | None:
        """The first boardable departure from a stop at or after a moment.

        Scans yesterday's, today's and tomorrow's service dates and returns the
        earliest departure at or after ``after``.

        Yesterday matters and is easy to miss. GTFS models a trip that runs past
        midnight as belonging to the day it *started*, with an hours field that
        keeps counting: the 00:45 train on the 18th is stored under service date
        the 17th at ``24:45:00`` (88_500 s). The DMRC feed really does this --
        1,410 stop_times depart at or after 24:00:00, the latest at 25:13. So a
        commuter standing on a platform at 00:30 asking "when is my next train"
        can only be answered correctly by looking at *yesterday's* service. This
        used to scan (0, 1) only, told them the next train was tomorrow morning,
        and hid a train that was 15 minutes away -- at the exact hour the answer
        matters most.

        Ordering is by real ``departure_at``, not by which service date we
        happened to try first, since two service dates can both be in play
        around midnight.
        """
        candidates: list[LastTrainInfo] = []
        local = after.astimezone(self._tz)
        for day_offset in (-1, 0, 1):
            service_date = local.date() + timedelta(days=day_offset)
            midnight = datetime.combine(service_date, time(0), tzinfo=self._tz)
            # For yesterday this exceeds 86_400, which is exactly how a
            # ">= 24:00:00" departure gets selected.
            min_seconds = max(int((after - midnight).total_seconds()), 0)
            info = await self._first_departure_after(
                session, stop_id, service_date, min_seconds, route_id, direction_id
            )
            if info is not None:
                candidates.append(info)
        if not candidates:
            return None
        return min(candidates, key=lambda i: i.departure_at)

    async def _first_departure_after(
        self,
        session: AsyncSession,
        stop_id: str,
        service_date: date,
        min_seconds: int,
        route_id: str | None,
        direction_id: int | None,
    ) -> LastTrainInfo | None:
        active = await self.active_service_ids(session, service_date)
        if not active:
            return None
        terminal_stop_time = aliased(StopTime)
        terminal_seq = (
            select(func.max(terminal_stop_time.stop_sequence))
            .where(terminal_stop_time.trip_id == StopTime.trip_id)
            .scalar_subquery()
        )
        stmt = (
            select(StopTime, Trip)
            .join(Trip, Trip.trip_id == StopTime.trip_id)
            .where(
                StopTime.stop_id == stop_id,
                Trip.service_id.in_(active),
                StopTime.stop_sequence < terminal_seq,
                StopTime.departure_seconds >= min_seconds,
            )
        )
        if route_id is not None:
            stmt = stmt.where(Trip.route_id == route_id)
        if direction_id is not None:
            stmt = stmt.where(Trip.direction_id == direction_id)
        row = (
            await session.execute(stmt.order_by(StopTime.departure_seconds).limit(1))
        ).first()
        if row is None:
            return None
        stop_time, trip = row[0], row[1]
        midnight = datetime.combine(service_date, time(0), tzinfo=self._tz)
        return LastTrainInfo(
            stop_id=stop_id,
            route_id=trip.route_id,
            trip_id=trip.trip_id,
            direction_id=trip.direction_id,
            headsign=trip.trip_headsign,
            service_date=service_date,
            departure_seconds=stop_time.departure_seconds,
            departure_at=midnight + timedelta(seconds=stop_time.departure_seconds),
        )

    async def due_reminders(
        self, session: AsyncSession, now: datetime
    ) -> list[tuple[LastTrainReminder, LastTrainInfo]]:
        """Enabled reminders inside their notification window right now.

        A reminder is due when ``departure - lead <= now < departure`` for the
        relevant service date and it hasn't fired for that date yet. Callers
        must set ``last_notified_service_date`` after notifying.
        """
        local_now = now.astimezone(self._tz)
        candidate_dates = [local_now.date()]
        if local_now.hour < 4:
            # Post-midnight departures belong to yesterday's service day.
            candidate_dates.append(local_now.date() - timedelta(days=1))

        due: list[tuple[LastTrainReminder, LastTrainInfo]] = []
        reminders = await LastTrainReminderRepository(session).list_enabled()
        for reminder in reminders:
            info = await self._due_info(session, reminder, candidate_dates, now)
            if info is not None:
                due.append((reminder, info))
        return due

    async def _due_info(
        self,
        session: AsyncSession,
        reminder: LastTrainReminder,
        candidate_dates: Sequence[date],
        now: datetime,
    ) -> LastTrainInfo | None:
        for service_date in candidate_dates:
            if reminder.last_notified_service_date == service_date:
                continue
            info = await self.last_departure(
                session,
                reminder.stop_id,
                service_date,
                route_id=reminder.route_id,
                direction_id=reminder.direction_id,
            )
            if info is None:
                continue
            lead = timedelta(minutes=reminder.lead_minutes)
            if info.departure_at - lead <= now < info.departure_at:
                return info
        return None
