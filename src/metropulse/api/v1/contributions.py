"""Rider-contributed station knowledge.

Opt-in and in-the-moment: the client asks one small question after a journey
("which coach were you in?") rather than harvesting anything in the background.
A report is always a deliberate act by a signed-in rider, because confirmation
counts people and an anonymous vote cannot be counted.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_current_user, get_session
from metropulse.application.commuter.contributions import ContributionService
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.commuter_models import User

router = APIRouter(tags=["contributions"])


class CoachExitReportIn(BaseModel):
    """"Coach N was nearest to exit E when I got off here.\""""

    stop_id: str = Field(min_length=1, max_length=64)
    exit_id: int
    coach_index: int = Field(ge=0)
    route_id: str | None = Field(default=None, max_length=64)
    direction_id: int | None = None


class ContributionAcceptedOut(BaseModel):
    """What the rider's report achieved, stated plainly.

    ``confirmations`` is returned so the app can thank someone honestly —
    "you're the first to report this" reads very differently from "that's
    confirmed now", and both are true at different moments.
    """

    accepted: bool
    confirmations: int
    confirmed: bool
    was_new: bool


@router.post(
    "/contributions/coach-exit",
    response_model=ContributionAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def report_coach_exit(
    body: CoachExitReportIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ContributionAcceptedOut:
    """Report which coach stops nearest an exit."""
    try:
        outcome = await ContributionService().report_coach_exit(
            session,
            user_id=user.id,
            stop_id=body.stop_id,
            exit_id=body.exit_id,
            coach_index=body.coach_index,
            route_id=body.route_id,
            direction_id=body.direction_id,
        )
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return ContributionAcceptedOut(
        accepted=outcome.accepted,
        confirmations=outcome.confirmations,
        confirmed=outcome.confirmed,
        was_new=outcome.was_new,
    )
