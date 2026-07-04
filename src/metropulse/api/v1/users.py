"""User registration and profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_commuter, get_current_user, get_session
from metropulse.api.schemas_commuter import MeOut, RegisterIn, RegisterOut
from metropulse.infrastructure.db.commuter_models import User
from metropulse.wiring import CommuterServices

router = APIRouter(tags=["users"])


@router.post("/users", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterIn,
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> RegisterOut:
    """Register a device (or rotate the token of an existing one).

    The returned token is shown exactly once; store it securely on-device.
    """
    user, token, created = await services.users.register(
        session, body.device_id, body.platform
    )
    await session.commit()
    return RegisterOut(user_id=user.id, token=token, created=created)


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(get_current_user)) -> MeOut:
    """The authenticated user's profile."""
    return MeOut.model_validate(user)
