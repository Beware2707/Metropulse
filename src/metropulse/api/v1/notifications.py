"""Per-user notification endpoints (poll-based inbox)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_commuter, get_current_user, get_session
from metropulse.api.schemas_commuter import NotificationListOut, NotificationOut
from metropulse.infrastructure.db.commuter_models import User
from metropulse.wiring import CommuterServices

router = APIRouter(prefix="/me/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> NotificationListOut:
    """The user's notifications, newest first."""
    rows = await services.notifications.list_for_user(session, user.id, limit)
    return NotificationListOut(
        count=len(rows), notifications=[NotificationOut.model_validate(r) for r in rows]
    )


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notification_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> None:
    """Mark one notification as read."""
    marked = await services.notifications.mark_read(session, user.id, notification_id)
    if not marked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="notification not found")
    await session.commit()
