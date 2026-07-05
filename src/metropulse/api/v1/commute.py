"""The personalised commute card endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_commuter, get_current_user, get_session
from metropulse.api.schemas_commuter import CommuteCardOut
from metropulse.application.commuter.commute_card import NoCommuteConfiguredError
from metropulse.domain.entities import utcnow
from metropulse.domain.exceptions import NoRouteError, UnknownEntityError
from metropulse.infrastructure.db.commuter_models import User
from metropulse.wiring import CommuterServices

router = APIRouter(tags=["commute"])


@router.get("/me/commute-card", response_model=CommuteCardOut)
async def commute_card(
    walk_minutes: int = Query(default=10, ge=0, le=120),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> CommuteCardOut:
    """Everything a daily commuter needs: when to leave, what to board.

    Requires two favourite stations (label them Home and Work); the
    direction flips automatically by time of day.
    """
    try:
        card = await services.commute_card.build(
            session, user.id, now=utcnow(), walk_minutes=walk_minutes
        )
    except NoCommuteConfiguredError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except NoRouteError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CommuteCardOut(
        greeting=card.greeting,
        origin_stop_id=card.origin_stop_id,
        origin_name=card.origin_name,
        destination_stop_id=card.destination_stop_id,
        destination_name=card.destination_name,
        route_long_name=card.route_long_name,
        route_color=card.route_color,
        platform_hint=card.platform_hint,
        next_departure_at=card.next_departure_at,
        leave_by=card.leave_by,
        leave_in_seconds=card.leave_in_seconds,
        crowding=card.crowding,
        recommended_coach=card.recommended_coach,
        interchange_names=list(card.interchange_names),
        travel_seconds=card.travel_seconds,
        expected_arrival_at=card.expected_arrival_at,
        stations_remaining=card.stations_remaining,
    )
