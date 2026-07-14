"""Fare-advisor endpoint (authenticated): estimated spend + card/off-peak savings.

Schemas live here to stay conflict-free with parallel schema-file work.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_current_user, get_session
from metropulse.application.commuter.fare_advisor import FareAdvisorService
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.commuter_models import User

router = APIRouter(tags=["fare-advisor"])


class FareAdvisorOut(BaseModel):
    """Estimated fares and potential savings over the recent window."""

    window_days: int
    trips: int
    estimated_spend_inr: int
    card_saving_inr: int
    offpeak_extra_saving_inr: int
    note: str


@router.get("/me/fare-advisor", response_model=FareAdvisorOut)
async def fare_advisor(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FareAdvisorOut:
    """What your recent trips cost, and what a smart card / off-peak would save.

    All figures are estimates from DMRC's published fare slabs. Zero trips
    returns zeros with an explanatory note. 401 without a valid bearer token.
    """
    advice = await FareAdvisorService().summary(session, user.id, utcnow())
    return FareAdvisorOut(
        window_days=advice.window_days,
        trips=advice.trips,
        estimated_spend_inr=advice.estimated_spend_inr,
        card_saving_inr=advice.card_saving_inr,
        offpeak_extra_saving_inr=advice.offpeak_extra_saving_inr,
        note=advice.note,
    )
