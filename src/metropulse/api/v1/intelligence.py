"""Metro Intelligence: commute prediction, delay estimation, and smart
route/coach/exit recommendations — all derived from GTFS schedules and the
user's own journey history, never a black-box model.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_commuter, get_current_user, get_session
from metropulse.api.schemas_commuter import (
    CommutePredictionOut,
    DelayEstimateOut,
    InferredPlaceOut,
    SmartRecommendationOut,
)
from metropulse.domain.entities import utcnow
from metropulse.domain.exceptions import NoRouteError, UnknownEntityError
from metropulse.infrastructure.db.commuter_models import User
from metropulse.wiring import CommuterServices

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/me/commute-prediction", response_model=CommutePredictionOut)
async def predict_commute(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> CommutePredictionOut:
    """Predict the commute this user is most likely making right now, learned
    from their own journey history."""
    try:
        prediction = await services.commute_predictor.predict(session, user.id, utcnow())
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return CommutePredictionOut.from_domain(prediction)


@router.get("/me/inferred-places", response_model=list[InferredPlaceOut])
async def inferred_places(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> list[InferredPlaceOut]:
    """Places inferred from this user's journey history (Home, and a regular
    weekday destination) — suggestions for the client to offer, e.g. as
    pre-filled Favourites labels. Never written on the user's behalf."""
    places = await services.place_roles.infer(session, user.id, utcnow())
    return [InferredPlaceOut.from_domain(place) for place in places]


@router.get("/delay-estimate", response_model=DelayEstimateOut)
async def estimate_delay(
    route_id: str,
    direction_id: int | None = Query(default=None, ge=0, le=1),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> DelayEstimateOut:
    """Typical delay for a route around the current time of day, from
    historical completed journeys."""
    estimate = await services.delay_predictor.estimate(
        session, route_id, direction_id, utcnow()
    )
    return DelayEstimateOut.from_domain(estimate)


@router.get("/recommendations", response_model=SmartRecommendationOut)
async def recommend(
    origin: str,
    destination: str,
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> SmartRecommendationOut:
    """Best route, departure time, coach and exit for a trip."""
    try:
        recommendation = await services.smart_recommendations.recommend(
            session, origin, destination, utcnow()
        )
    except (UnknownEntityError, NoRouteError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return SmartRecommendationOut.from_domain(recommendation)
