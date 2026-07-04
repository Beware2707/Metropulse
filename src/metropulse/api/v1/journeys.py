"""Journey tracking endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_commuter, get_current_user, get_session
from metropulse.api.schemas_commuter import JourneyIn, JourneyListOut, JourneyOut
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.commuter_models import User
from metropulse.wiring import CommuterServices

router = APIRouter(prefix="/me/journeys", tags=["journeys"])


@router.post("", response_model=JourneyOut, status_code=status.HTTP_201_CREATED)
async def start_journey(
    body: JourneyIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> JourneyOut:
    """Start a journey; any previously active journey is superseded."""
    try:
        journey = await services.journeys.start(
            session,
            user.id,
            body.origin_stop_id,
            body.destination_stop_id,
            vehicle_id=body.vehicle_id,
            route_id=body.route_id,
            interchange_stop_ids=body.interchange_stop_ids,
        )
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    await session.commit()
    return JourneyOut.model_validate(journey)


@router.get("/current", response_model=JourneyOut)
async def current_journey(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> JourneyOut:
    """The user's active journey (404 when none)."""
    journey = await services.journeys.current(session, user.id)
    if journey is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no active journey")
    return JourneyOut.model_validate(journey)


@router.get("", response_model=JourneyListOut)
async def journey_history(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> JourneyListOut:
    """The user's journey history, newest first."""
    journeys = await services.journeys.history(session, user.id, limit)
    return JourneyListOut(
        count=len(journeys), journeys=[JourneyOut.model_validate(j) for j in journeys]
    )


@router.post("/{journey_id}/complete", response_model=JourneyOut)
async def complete_journey(
    journey_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> JourneyOut:
    """Complete an active journey."""
    journey = await services.journeys.complete(session, user.id, journey_id)
    if journey is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="active journey not found")
    await session.commit()
    return JourneyOut.model_validate(journey)


@router.post("/{journey_id}/abandon", response_model=JourneyOut)
async def abandon_journey(
    journey_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> JourneyOut:
    """Abandon an active journey."""
    journey = await services.journeys.abandon(session, user.id, journey_id)
    if journey is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="active journey not found")
    await session.commit()
    return JourneyOut.model_validate(journey)
