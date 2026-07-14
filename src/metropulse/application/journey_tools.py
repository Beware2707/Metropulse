"""Timetable tools layered on the journey planner: latest departure, reach, meet.

Algorithm notes
---------------

``latest_departure`` reuses the planner twice over:

1. The existing forward :class:`JourneyPlanner` picks the route *shape* (the
   sequence of ride legs and walking transfers between them).
2. An exact **backward pass over the published timetable** then assigns real
   trips to that shape: walking legs shift the deadline earlier by their walk
   time (which already includes the transfer overhead), and each ride leg is
   resolved to the latest same-service-day trip whose arrival at the
   interchange still meets the deadline of the leg that follows it. The first
   leg's boarding time is therefore the latest feasible departure.

   A full timetable-wide backward profile search (reverse CSA) was considered
   but rejected: the planner's graph is pattern-based (frequency-agnostic), so
   a separate engine would duplicate its interchange/walk modelling for no
   practical gain on a metro network where the fastest route shape is also the
   last-train route shape in all but pathological cases.

``reach`` exposes the planner's own Dijkstra run one-to-all (no target), so
one search settles the whole 262-stop network; minutes are the planner's
expected travel time (boarding wait included), which keeps the numbers
consistent with ``/journey/plan`` and makes ``meet`` deterministic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from metropulse.application.commuter.last_train import LastTrainService
from metropulse.application.journey_planner import JourneyPlanner
from metropulse.domain.journey import RideLeg, WalkLeg
from metropulse.infrastructure.db.models import Stop, StopTime, Trip

#: Minimum seconds between alighting and re-boarding at the *same* station
#: (walking transfers carry their own overhead inside walk_seconds).
INTERCHANGE_BUFFER_SECONDS = 120


@dataclass(frozen=True, slots=True)
class LatestDepartureLeg:
    """One ride of the latest-departure chain, with its real boarding time."""

    route_long_name: str | None
    route_color: str | None
    board_stop_id: str
    board_name: str
    alight_stop_id: str
    alight_name: str
    headsign: str
    last_departure: datetime


@dataclass(frozen=True, slots=True)
class LatestDeparturePlan:
    """The latest same-service-day journey that still completes."""

    origin: str
    destination: str
    depart_by: datetime
    arrive_by: datetime
    total_minutes: int
    legs: tuple[LatestDepartureLeg, ...]


@dataclass(frozen=True, slots=True)
class MeetCandidate:
    """A meeting-point station scored for two travellers."""

    stop_id: str
    name: str
    minutes_a: int
    minutes_b: int
    max_minutes: int
    total_minutes: int


class JourneyTools:
    """Latest-departure / reach / meet computations over the loaded GTFS."""

    def __init__(self, planner: JourneyPlanner, last_train: LastTrainService) -> None:
        self._planner = planner
        self._last_train = last_train

    @property
    def tz(self) -> ZoneInfo:
        """The network's local timezone."""
        return self._last_train.tz

    async def latest_departure(
        self,
        session: AsyncSession,
        origin: str,
        destination: str,
        on_date: date | None = None,
    ) -> LatestDeparturePlan | None:
        """The latest departure from origin today that still completes.

        Returns ``None`` when no same-service-day trip chain exists (no
        active service, a leg with no feasible trip, or a walking-only
        journey, which has no timetable to bound it). Raises
        :class:`UnknownEntityError` / :class:`NoRouteError` from the planner
        for unknown stops or a disconnected pair.
        """
        service_date = on_date or datetime.now(self.tz).date()
        plan = await self._planner.plan(origin, destination)
        active = await self._last_train.active_service_ids(session, service_date)
        if not active:
            return None

        # Backward pass: walk legs shift the deadline earlier; ride legs pick
        # the latest trip arriving by the deadline of whatever follows them.
        deadline: int | None = None
        later_is_ride = False
        chosen: list[tuple[RideLeg, int, int, str | None]] = []
        for leg in reversed(plan.legs):
            if isinstance(leg, WalkLeg):
                if deadline is not None:
                    deadline -= int(round(leg.walk_seconds))
                later_is_ride = False
                continue
            arrival_deadline = deadline
            if arrival_deadline is not None and later_is_ride:
                arrival_deadline -= INTERCHANGE_BUFFER_SECONDS
            resolved = await self._latest_trip(session, active, leg, arrival_deadline)
            if resolved is None:
                return None
            departure_seconds, arrival_seconds, headsign = resolved
            chosen.append((leg, departure_seconds, arrival_seconds, headsign))
            deadline = departure_seconds
            later_is_ride = True
        if not chosen:
            return None  # walking-only journey: no timetable to bound it
        chosen.reverse()

        lead_walk, trail_walk = _boundary_walk_seconds(plan.legs)
        depart_by_seconds = chosen[0][1] - lead_walk
        arrive_by_seconds = chosen[-1][2] + trail_walk
        midnight = datetime.combine(service_date, time(0), tzinfo=self.tz)
        return LatestDeparturePlan(
            origin=origin,
            destination=destination,
            depart_by=midnight + timedelta(seconds=depart_by_seconds),
            arrive_by=midnight + timedelta(seconds=arrive_by_seconds),
            total_minutes=math.ceil((arrive_by_seconds - depart_by_seconds) / 60),
            legs=tuple(
                LatestDepartureLeg(
                    route_long_name=leg.route_long_name,
                    route_color=leg.route_color,
                    board_stop_id=leg.board.stop_id,
                    board_name=leg.board.name,
                    alight_stop_id=leg.alight.stop_id,
                    alight_name=leg.alight.name,
                    headsign=headsign or leg.platform_hint,
                    last_departure=midnight + timedelta(seconds=departure_seconds),
                )
                for leg, departure_seconds, _, headsign in chosen
            ),
        )

    async def reach(self, origin: str) -> dict[str, int]:
        """Fastest expected travel minutes from origin to every reachable stop.

        Exposes the planner's Dijkstra run one-to-all; minutes include the
        boarding-wait penalty and are rounded up. The origin maps to 0.
        Raises :class:`UnknownEntityError` for an unknown origin.
        """
        seconds = await self._planner.travel_seconds_from(origin)
        return {
            stop_id: math.ceil(travel / 60) for stop_id, travel in seconds.items()
        }

    async def meet(
        self, session: AsyncSession, a: str, b: str, limit: int = 10
    ) -> list[MeetCandidate]:
        """Fairest meeting stations for two travellers.

        Intersects ``reach(a)`` and ``reach(b)`` and ranks by the slower
        traveller's minutes first (fairness), then combined minutes, then
        stop_id for determinism. Raises :class:`UnknownEntityError` for
        unknown stops.
        """
        reach_a = await self.reach(a)
        reach_b = await self.reach(b)
        common = sorted(reach_a.keys() & reach_b.keys())
        names = await _stop_names(session, common)
        candidates = [
            MeetCandidate(
                stop_id=stop_id,
                name=names.get(stop_id, stop_id),
                minutes_a=reach_a[stop_id],
                minutes_b=reach_b[stop_id],
                max_minutes=max(reach_a[stop_id], reach_b[stop_id]),
                total_minutes=reach_a[stop_id] + reach_b[stop_id],
            )
            for stop_id in common
        ]
        candidates.sort(key=lambda c: (c.max_minutes, c.total_minutes, c.stop_id))
        return candidates[:limit]

    async def _latest_trip(
        self,
        session: AsyncSession,
        active_service_ids: set[str],
        leg: RideLeg,
        arrival_deadline: int | None,
    ) -> tuple[int, int, str | None] | None:
        """Latest same-day trip riding this leg, or None.

        Returns (departure_seconds at board, arrival_seconds at alight,
        trip headsign) for the trip on the leg's route/direction that departs
        the boarding stop latest while still arriving by ``arrival_deadline``
        (unbounded when None, i.e. the journey's final ride).
        """
        board_st = aliased(StopTime)
        alight_st = aliased(StopTime)
        stmt = (
            select(board_st.departure_seconds, alight_st.arrival_seconds, Trip.trip_headsign)
            .join(Trip, Trip.trip_id == board_st.trip_id)
            .join(alight_st, alight_st.trip_id == board_st.trip_id)
            .where(
                board_st.stop_id == leg.board.stop_id,
                alight_st.stop_id == leg.alight.stop_id,
                board_st.stop_sequence < alight_st.stop_sequence,
                Trip.route_id == leg.route_id,
                Trip.service_id.in_(active_service_ids),
            )
        )
        if leg.direction_id is not None:
            stmt = stmt.where(Trip.direction_id == leg.direction_id)
        if arrival_deadline is not None:
            stmt = stmt.where(alight_st.arrival_seconds <= arrival_deadline)
        stmt = stmt.order_by(board_st.departure_seconds.desc()).limit(1)
        row = (await session.execute(stmt)).first()
        if row is None:
            return None
        return int(row[0]), int(row[1]), row[2]


def _boundary_walk_seconds(legs: tuple[RideLeg | WalkLeg, ...]) -> tuple[int, int]:
    """(walk seconds before the first ride, walk seconds after the last ride)."""
    ride_indexes = [i for i, leg in enumerate(legs) if isinstance(leg, RideLeg)]
    if not ride_indexes:
        return 0, 0
    lead = sum(
        int(round(leg.walk_seconds))
        for leg in legs[: ride_indexes[0]]
        if isinstance(leg, WalkLeg)
    )
    trail = sum(
        int(round(leg.walk_seconds))
        for leg in legs[ride_indexes[-1] + 1 :]
        if isinstance(leg, WalkLeg)
    )
    return lead, trail


async def _stop_names(session: AsyncSession, stop_ids: list[str]) -> dict[str, str]:
    """stop_id -> stop_name for the given ids."""
    if not stop_ids:
        return {}
    rows = (
        await session.execute(select(Stop).where(Stop.stop_id.in_(stop_ids)))
    ).scalars()
    return {stop.stop_id: stop.stop_name for stop in rows}
