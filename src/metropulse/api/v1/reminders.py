"""Last-train lookup (public) and last-train reminders (per-user)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_commuter, get_current_user, get_session
from metropulse.api.schemas_commuter import LastTrainOut, ReminderIn, ReminderOut
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.commuter_models import LastTrainReminder, User
from metropulse.infrastructure.db.commuter_repositories import (
    LastTrainReminderRepository,
)
from metropulse.infrastructure.db.repositories import StopRepository
from metropulse.wiring import CommuterServices

router = APIRouter(tags=["last-train"])


@router.get("/stations/{stop_id}/last-train", response_model=LastTrainOut)
async def last_train(
    stop_id: str,
    route_id: str | None = None,
    direction_id: int | None = Query(default=None, ge=0, le=1),
    service_date: date | None = Query(default=None, alias="date"),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> LastTrainOut:
    """The last boardable departure from a station for a service date.

    Defaults to today in the network's local timezone.
    """
    if await StopRepository(session).get(stop_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"station '{stop_id}' not found")
    resolved_date = service_date or utcnow().astimezone(services.last_train.tz).date()
    info = await services.last_train.last_departure(
        session, stop_id, resolved_date, route_id=route_id, direction_id=direction_id
    )
    if info is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="no boardable departure found for that date/filters",
        )
    return LastTrainOut.from_domain(info)


@router.post(
    "/me/reminders/last-train",
    response_model=ReminderOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_reminder(
    body: ReminderIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ReminderOut:
    """Create a last-train reminder."""
    if await StopRepository(session).get(body.stop_id) is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"station '{body.stop_id}' not found"
        )
    reminder = LastTrainReminder(
        user_id=user.id,
        stop_id=body.stop_id,
        route_id=body.route_id,
        direction_id=body.direction_id,
        lead_minutes=body.lead_minutes,
        enabled=True,
        created_at=utcnow(),
    )
    LastTrainReminderRepository(session).add(reminder)
    await session.commit()
    return ReminderOut.model_validate(reminder)


@router.get("/me/reminders/last-train", response_model=list[ReminderOut])
async def list_reminders(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ReminderOut]:
    """The user's last-train reminders."""
    rows = await LastTrainReminderRepository(session).list_for_user(user.id)
    return [ReminderOut.model_validate(r) for r in rows]


@router.delete(
    "/me/reminders/last-train/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_reminder(
    reminder_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete one of the user's reminders."""
    removed = await LastTrainReminderRepository(session).delete(user.id, reminder_id)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="reminder not found")
    await session.commit()
