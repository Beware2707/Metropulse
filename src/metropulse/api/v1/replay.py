"""Commute Replay: what a completed trip (or a month of them) actually cost
and saved — Spotify-Wrapped-style, but for the metro."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_commuter, get_current_user, get_session
from metropulse.api.schemas_commuter import MonthlyReplayOut, TripReplayOut
from metropulse.domain.entities import utcnow
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.commuter_models import User
from metropulse.wiring import CommuterServices

router = APIRouter(prefix="/me/replay", tags=["replay"])


@router.get("/latest-trip", response_model=TripReplayOut)
async def latest_trip_replay(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> TripReplayOut:
    """The user's most recently completed trip, replayed."""
    try:
        replay = await services.commute_impact.latest_trip(session, user.id)
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TripReplayOut.from_domain(replay)


@router.get("/monthly", response_model=MonthlyReplayOut)
async def monthly_replay(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> MonthlyReplayOut:
    """A rolling 30-day summary of the user's completed trips."""
    replay = await services.commute_impact.monthly_summary(session, user.id, utcnow())
    return MonthlyReplayOut.from_domain(replay)
