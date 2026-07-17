"""Coach/exit recommendations, crowd reports, and exit curation (admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import (
    get_commuter,
    get_current_user,
    get_session,
    require_admin,
)
from metropulse.api.schemas_commuter import (
    CoachExitHintIn,
    CoachRecommendationOut,
    CrowdReportIn,
    ExitRecommendationOut,
    StationExitIn,
    StationExitOut,
)
from metropulse.domain.entities import utcnow
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.commuter_models import CrowdObservation, User
from metropulse.infrastructure.db.commuter_repositories import (
    CrowdObservationRepository,
)
from metropulse.wiring import CommuterServices

router = APIRouter(tags=["recommendations"])


@router.get("/recommendations/coach", response_model=CoachRecommendationOut)
async def recommend_coach(
    origin: str,
    destination: str,
    route_id: str | None = None,
    direction_id: int | None = Query(default=None, ge=0, le=1),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> CoachRecommendationOut:
    """Which coach to board: crowding + exit alignment at the destination."""
    try:
        recommendation = await services.coach.recommend(
            session, origin, destination, route_id, direction_id, at=utcnow()
        )
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return CoachRecommendationOut.from_domain(recommendation)


@router.get("/recommendations/exit", response_model=ExitRecommendationOut)
async def recommend_exit(
    station: str,
    landmark: str | None = None,
    route_id: str | None = None,
    direction_id: int | None = Query(default=None, ge=0, le=1),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> ExitRecommendationOut:
    """Which exit to take at a station, optionally matched to a landmark."""
    try:
        recommendation = await services.exits.recommend(
            session, station, landmark=landmark, route_id=route_id,
            direction_id=direction_id,
        )
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not recommendation.exits:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="no exits curated for this station"
        )
    return ExitRecommendationOut.from_domain(recommendation)


@router.post("/crowd/reports", status_code=status.HTTP_202_ACCEPTED)
async def report_crowding(
    body: CrowdReportIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Submit a crowding observation (feeds the coach recommendation engine)."""
    CrowdObservationRepository(session).add(
        CrowdObservation(
            route_id=body.route_id,
            direction_id=body.direction_id,
            stop_id=body.stop_id,
            vehicle_id=body.vehicle_id,
            coach_index=body.coach_index,
            occupancy=(body.level - 1) / 4.0,  # 1..5 -> 0.0..1.0
            observed_at=utcnow(),
            source="user",
            confidence=0.5,
            payload={"reported_by": user.id},
        )
    )
    await session.commit()
    return {"status": "accepted"}


@router.get("/stations/{stop_id}/exits", response_model=list[StationExitOut])
async def list_station_exits(
    stop_id: str,
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> list[StationExitOut]:
    """All curated exits of a station, with nearby landmarks."""
    exits = await services.exits.list_exits(session, stop_id)
    return [StationExitOut.from_exit(e) for e in exits]


@router.post(
    "/admin/stations/{stop_id}/exits",
    response_model=StationExitOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def add_station_exit(
    stop_id: str,
    body: StationExitIn,
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> StationExitOut:
    """Curate a new station exit (admin)."""
    try:
        exit_row = await services.exits.add_exit(
            session,
            stop_id,
            body.name,
            description=body.description,
            latitude=body.latitude,
            longitude=body.longitude,
            landmarks=body.landmarks,
        )
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return StationExitOut.model_validate(exit_row)


@router.post(
    "/admin/coach-exit-hints",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def add_coach_exit_hint(
    body: CoachExitHintIn,
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> dict[str, int]:
    """Curate a coach-exit alignment hint (admin)."""
    try:
        hint = await services.exits.add_hint(
            session,
            body.stop_id,
            body.exit_id,
            body.coach_index,
            route_id=body.route_id,
            direction_id=body.direction_id,
        )
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return {"hint_id": hint.id}
