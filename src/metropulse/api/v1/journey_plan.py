"""Journey planning endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_commuter
from metropulse.api.deps import get_session
from metropulse.api.schemas_commuter import CrowdForecastOut, JourneyPlanOut
from metropulse.domain.exceptions import NoRouteError, UnknownEntityError
from metropulse.wiring import CommuterServices

router = APIRouter(tags=["journey"])

RoutePreference = Literal["fastest", "fewer_transfers", "less_walking"]


@router.get("/journey/plan", response_model=JourneyPlanOut)
async def plan_journey(
    origin: str,
    destination: str,
    departure_at: datetime | None = None,
    preference: RoutePreference = "fastest",
    services: CommuterServices = Depends(get_commuter),
) -> JourneyPlanOut:
    """Best route between two stations: legs, interchanges, walking, timing.

    ``preference`` biases which route is selected among the three supported
    modes; the returned timing always reflects the real schedule-derived
    duration of whichever route is chosen, never an inflated preference
    weight. Wheelchair-accessible routing is not yet supported by this
    dataset — callers should not assume any accessibility guarantee.

    The ``interchange_stop_ids`` in the response can be passed straight into
    ``POST /me/journeys`` to receive interchange reminders while riding.
    """
    try:
        plan = await services.planner.plan(
            origin, destination, departure_at, preference=preference
        )
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NoRouteError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return JourneyPlanOut.from_domain(plan)


@router.get("/journey/crowd-forecast", response_model=CrowdForecastOut)
async def crowd_forecast(
    stops: str = Query(..., description="comma-separated stop ids: origin, interchanges, destination"),
    departure_at: datetime | None = None,
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> CrowdForecastOut:
    """Typical crowding along a planned route, from DMRC's measured hourly
    ridership -- averages over the period named in the response, never a live
    reading. Suggests a nearby quieter departure only when it is meaningfully
    quieter (the busiest station at least 15 points lower)."""
    stop_ids = [s.strip() for s in stops.split(",") if s.strip()]
    if not stop_ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="no stops given")
    when = departure_at or datetime.now(tz=None).astimezone()
    forecast = await services.crowd_forecast.forecast(session, stop_ids, when)
    return CrowdForecastOut.from_domain(forecast)
