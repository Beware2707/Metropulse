"""Whether the loaded timetable actually covers today.

The distinction this module exists to draw is between two things that look
identical in the app and mean opposite things to a rider:

    "no trains are running right now"        -> the network is quiet/closed
    "we have no timetable data for today"    -> we simply do not know

MetroPulse's own GTFS is a live example of the second. Its ``calendar.txt``
declares a ``sunday`` service that runs on Sundays — and **not one trip
references it** (5,379 weekday trips, 59 Saturday, 0 Sunday). So on a Sunday
every arrivals board is empty and every screen said "No trains headed this way
right now", which reads as *the metro isn't running*. Delhi Metro runs fine on
Sundays; we just cannot see it.

Note why the obvious check is not enough: ``active_service_ids`` answers from
the calendar, and on a Sunday it returns ``{"sunday"}`` — non-empty, so
"is there service today?" looks like yes. The honest answer requires counting
the TRIPS attached to those services, which is what this does.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.commuter.last_train import LastTrainService
from metropulse.infrastructure.db.models import Trip


@dataclass(frozen=True, slots=True)
class ServiceDayCoverage:
    """What the timetable knows about one service date."""

    service_date: date
    #: Service ids the calendar marks active — may be non-empty while no trip
    #: uses any of them, which is precisely the case this class detects.
    active_service_ids: tuple[str, ...]
    #: Trips actually scheduled under those services. Zero means blind.
    scheduled_trips: int

    @property
    def has_timetable(self) -> bool:
        """True when we can say anything at all about today's trains."""
        return self.scheduled_trips > 0


class ServiceDayService:
    """Answers 'do we have a timetable for this date?' honestly."""

    def __init__(self, last_train: LastTrainService) -> None:
        self._last_train = last_train

    async def coverage(self, session: AsyncSession, on: date) -> ServiceDayCoverage:
        active = await self._last_train.active_service_ids(session, on)
        if not active:
            return ServiceDayCoverage(
                service_date=on, active_service_ids=(), scheduled_trips=0
            )
        count = await session.scalar(
            select(func.count())
            .select_from(Trip)
            .where(Trip.service_id.in_(active))
        )
        return ServiceDayCoverage(
            service_date=on,
            active_service_ids=tuple(sorted(active)),
            scheduled_trips=int(count or 0),
        )
