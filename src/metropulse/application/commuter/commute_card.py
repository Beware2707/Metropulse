"""Commute card: one personalised answer to "when do I leave, what do I board".

Composes existing engines — favourites (Home/Work), the timetable
(next boardable departure), the journey planner (route, interchanges, travel
time), the crowd predictor and the coach recommender — into a single card.
Direction flips by time of day: Home→Work before noon, Work→Home after.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.commuter.coach import CoachRecommendationService
from metropulse.application.commuter.favourites import FavouritesService
from metropulse.application.commuter.last_train import LastTrainService
from metropulse.application.journey_planner import JourneyPlanner
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.domain.journey import JourneyPlan, RideLeg
from metropulse.infrastructure.db.repositories import StopRepository

logger = logging.getLogger(__name__)

_HOME_LABELS = ("home",)
_WORK_LABELS = ("work", "office")


@dataclass(frozen=True, slots=True)
class CommuteCard:
    """Everything the home screen needs for the daily commute."""

    greeting: str
    origin_stop_id: str
    origin_name: str
    destination_stop_id: str
    destination_name: str
    route_long_name: str | None
    route_color: str | None
    platform_hint: str | None
    next_departure_at: datetime | None
    leave_by: datetime | None
    leave_in_seconds: float | None
    crowding: str  # low | moderate | high | unknown
    recommended_coach: int | None
    interchange_names: tuple[str, ...]
    travel_seconds: float | None
    expected_arrival_at: datetime | None
    stations_remaining: int | None


class NoCommuteConfiguredError(UnknownEntityError):
    """Raised when the user hasn't set up Home/Work favourite stations."""


class CommuteCardService:
    """Builds the personalised commute card for a user."""

    def __init__(
        self,
        favourites: FavouritesService,
        last_train: LastTrainService,
        planner: JourneyPlanner,
        coach: CoachRecommendationService,
    ) -> None:
        self._favourites = favourites
        self._last_train = last_train
        self._planner = planner
        self._coach = coach

    async def build(
        self,
        session: AsyncSession,
        user_id: str,
        now: datetime,
        walk_minutes: int = 10,
    ) -> CommuteCard:
        """The commute card for ``now``.

        Raises :class:`NoCommuteConfiguredError` without two favourite
        stations and :class:`NoRouteError` when no path connects them.
        """
        origin_id, destination_id = await self._pick_endpoints(session, user_id, now)
        stops = StopRepository(session)
        origin = await stops.get(origin_id)
        destination = await stops.get(destination_id)
        if origin is None or destination is None:
            # A favourite can outlive a static reload that renamed its stop.
            raise NoCommuteConfiguredError(
                "a favourite station no longer exists in the current dataset"
            )

        plan = await self._planner.plan(origin_id, destination_id, departure_at=now)
        first_ride = next(
            (leg for leg in plan.legs if isinstance(leg, RideLeg)), None
        )

        departure = await self._last_train.next_departure(
            session,
            origin_id,
            after=now,
            route_id=first_ride.route_id if first_ride else None,
            direction_id=first_ride.direction_id if first_ride else None,
        )
        leave_by = (
            departure.departure_at - timedelta(minutes=walk_minutes)
            if departure
            else None
        )
        leave_in = (leave_by - now).total_seconds() if leave_by else None

        crowding, coach_index = await self._crowd_and_coach(
            session, origin_id, destination_id, first_ride, now
        )
        in_vehicle = _in_vehicle_seconds(plan)
        arrival = (
            departure.departure_at + timedelta(seconds=in_vehicle)
            if departure
            else None
        )
        return CommuteCard(
            greeting=_greeting(now.astimezone(self._last_train.tz)),
            origin_stop_id=origin_id,
            origin_name=origin.stop_name,
            destination_stop_id=destination_id,
            destination_name=destination.stop_name,
            route_long_name=first_ride.route_long_name if first_ride else None,
            route_color=first_ride.route_color if first_ride else None,
            platform_hint=first_ride.platform_hint if first_ride else None,
            next_departure_at=departure.departure_at if departure else None,
            leave_by=leave_by,
            leave_in_seconds=max(leave_in, 0.0) if leave_in is not None else None,
            crowding=crowding,
            recommended_coach=coach_index,
            interchange_names=tuple(s.name for s in plan.interchange_stops),
            travel_seconds=in_vehicle,
            expected_arrival_at=arrival,
            stations_remaining=len(plan.remaining_stations),
        )

    async def _pick_endpoints(
        self, session: AsyncSession, user_id: str, now: datetime
    ) -> tuple[str, str]:
        favourites = await self._favourites.list_stations(session, user_id)
        by_label = {
            (f.label or "").strip().lower(): f.stop_id for f in favourites
        }
        home = next((by_label[label] for label in _HOME_LABELS if label in by_label), None)
        work = next((by_label[label] for label in _WORK_LABELS if label in by_label), None)
        if home is None or work is None:
            # Fall back to the user's two top-ranked favourites.
            ordered = [f.stop_id for f in favourites]
            if len(ordered) < 2:
                raise NoCommuteConfiguredError(
                    "set two favourite stations (label them Home and Work) "
                    "to enable the commute card"
                )
            home, work = ordered[0], ordered[1]
        morning = now.astimezone(self._last_train.tz).hour < 12
        return (home, work) if morning else (work, home)

    async def _crowd_and_coach(
        self,
        session: AsyncSession,
        origin_id: str,
        destination_id: str,
        first_ride: RideLeg | None,
        now: datetime,
    ) -> tuple[str, int | None]:
        try:
            recommendation = await self._coach.recommend(
                session,
                origin_id,
                destination_id,
                first_ride.route_id if first_ride else None,
                first_ride.direction_id if first_ride else None,
                at=now,
            )
        except UnknownEntityError:
            return "unknown", None
        occupancies = [c.occupancy for c in recommendation.coaches]
        average = sum(occupancies) / len(occupancies) if occupancies else 0.0
        if average < 0.45:
            crowding = "low"
        elif average < 0.7:
            crowding = "moderate"
        else:
            crowding = "high"
        return crowding, recommendation.recommended_coach


def _in_vehicle_seconds(plan: JourneyPlan) -> float:
    """Journey time measured from boarding the first train.

    The initial platform wait is excluded — ``next_departure`` pins it down
    exactly and keeping the planner's generic estimate would double-count it.
    Interchange waits (second and later boardings) are kept.
    """
    total = 0.0
    rides_seen = 0
    for leg in plan.legs:
        if isinstance(leg, RideLeg):
            total += leg.ride_seconds
            if rides_seen > 0:
                total += leg.wait_seconds
            rides_seen += 1
        else:
            total += leg.walk_seconds
    return total


def _greeting(local_now: datetime) -> str:
    if local_now.hour < 12:
        return "Good morning"
    if local_now.hour < 17:
        return "Good afternoon"
    return "Good evening"
