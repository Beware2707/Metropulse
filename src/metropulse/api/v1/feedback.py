"""User-submitted app feedback (Sprint 4: beta launch)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_current_user, get_session
from metropulse.api.schemas_commuter import FeedbackIn
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.commuter_models import Feedback, User
from metropulse.infrastructure.db.commuter_repositories import FeedbackRepository

router = APIRouter(tags=["feedback"])


@router.post("/feedback", status_code=status.HTTP_202_ACCEPTED)
async def submit_feedback(
    body: FeedbackIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Submit in-app feedback -- a message, optionally categorised."""
    FeedbackRepository(session).add(
        Feedback(
            user_id=user.id,
            category=body.category,
            message=body.message,
            app_version=body.app_version,
            platform=body.platform,
            created_at=utcnow(),
        )
    )
    await session.commit()
    return {"status": "accepted"}
