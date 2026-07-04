"""Journey planning endpoint."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from metropulse.api.deps import get_commuter
from metropulse.api.schemas_commuter import JourneyPlanOut
from metropulse.domain.exceptions import NoRouteError, UnknownEntityError
from metropulse.wiring import CommuterServices

router = APIRouter(tags=["journey"])


@router.get("/journey/plan", response_model=JourneyPlanOut)
async def plan_journey(
    origin: str,
    destination: str,
    departure_at: datetime | None = None,
    services: CommuterServices = Depends(get_commuter),
) -> JourneyPlanOut:
    """Best route between two stations: legs, interchanges, walking, timing.

    The ``interchange_stop_ids`` in the response can be passed straight into
    ``POST /me/journeys`` to receive interchange reminders while riding.
    """
    try:
        plan = await services.planner.plan(origin, destination, departure_at)
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NoRouteError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return JourneyPlanOut.from_domain(plan)
