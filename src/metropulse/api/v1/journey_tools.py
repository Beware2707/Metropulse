"""Timetable-tool endpoints: latest departure, reach, meet.

Response schemas live here (not in api/schemas*.py) so this feature stays
self-contained and conflict-free with parallel work on shared schema files.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_commuter, get_session
from metropulse.application.journey_tools import JourneyTools, LatestDeparturePlan
from metropulse.domain.exceptions import NoRouteError, UnknownEntityError
from metropulse.wiring import CommuterServices

router = APIRouter(prefix="/journeys", tags=["journey-tools"])


class LatestDepartureLegOut(BaseModel):
    """One ride of the latest-departure chain."""

    route_long_name: str | None
    route_color: str | None
    board_stop_id: str
    board_name: str
    alight_stop_id: str
    alight_name: str
    headsign: str
    last_departure: str


class LatestDepartureOut(BaseModel):
    """The latest same-service-day journey that still completes."""

    origin: str
    destination: str
    depart_by: str
    arrive_by: str
    total_minutes: int
    legs: list[LatestDepartureLegOut]

    @classmethod
    def from_domain(cls, plan: LatestDeparturePlan) -> "LatestDepartureOut":
        """Build from the application value."""
        return cls(
            origin=plan.origin,
            destination=plan.destination,
            depart_by=plan.depart_by.isoformat(),
            arrive_by=plan.arrive_by.isoformat(),
            total_minutes=plan.total_minutes,
            legs=[
                LatestDepartureLegOut(
                    route_long_name=leg.route_long_name,
                    route_color=leg.route_color,
                    board_stop_id=leg.board_stop_id,
                    board_name=leg.board_name,
                    alight_stop_id=leg.alight_stop_id,
                    alight_name=leg.alight_name,
                    headsign=leg.headsign,
                    last_departure=leg.last_departure.isoformat(),
                )
                for leg in plan.legs
            ],
        )


class ReachOut(BaseModel):
    """One-to-all fastest travel minutes from an origin."""

    origin: str
    at: str
    reach: dict[str, int]


class MeetCandidateOut(BaseModel):
    """A meeting-point station scored for two travellers."""

    stop_id: str
    name: str
    minutes_a: int
    minutes_b: int
    max_minutes: int
    total_minutes: int


class MeetOut(BaseModel):
    """Fairest meeting stations for two travellers."""

    a: str
    b: str
    candidates: list[MeetCandidateOut]


def _tools(services: CommuterServices) -> JourneyTools:
    return JourneyTools(services.planner, services.last_train)


@router.get("/latest-departure", response_model=LatestDepartureOut)
async def latest_departure(
    origin: str,
    destination: str,
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> LatestDepartureOut:
    """The latest departure from origin today that still reaches destination.

    Every leg (including interchanges) is guaranteed to catch its final
    feasible trip of the service day, per the published timetable. 404 when
    either stop is unknown or no same-service-day path exists.
    """
    tools = _tools(services)
    try:
        plan = await tools.latest_departure(session, origin, destination)
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NoRouteError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if plan is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"no same-service-day journey from '{origin}' to '{destination}'",
        )
    return LatestDepartureOut.from_domain(plan)


@router.get("/reach", response_model=ReachOut)
async def reach(
    origin: str,
    at: datetime | None = None,
    services: CommuterServices = Depends(get_commuter),
) -> ReachOut:
    """Fastest arrival minutes from origin to every reachable station."""
    tools = _tools(services)
    try:
        minutes = await tools.reach(origin)
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    moment = at or datetime.now(tools.tz)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=tools.tz)
    return ReachOut(origin=origin, at=moment.isoformat(), reach=minutes)


@router.get("/meet", response_model=MeetOut)
async def meet(
    a: str,
    b: str,
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> MeetOut:
    """Top meeting stations for two travellers, fairness (max minutes) first."""
    tools = _tools(services)
    try:
        candidates = await tools.meet(session, a, b)
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MeetOut(
        a=a,
        b=b,
        candidates=[
            MeetCandidateOut(
                stop_id=c.stop_id,
                name=c.name,
                minutes_a=c.minutes_a,
                minutes_b=c.minutes_b,
                max_minutes=c.max_minutes,
                total_minutes=c.total_minutes,
            )
            for c in candidates
        ],
    )
