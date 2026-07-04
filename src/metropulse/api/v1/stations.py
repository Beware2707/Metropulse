"""Station endpoints: listing and per-station detail with serving routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_session
from metropulse.api.schemas import RouteOut, StationDetailOut, StationListOut, StationOut
from metropulse.infrastructure.db.repositories import StopRepository

router = APIRouter(tags=["stations"])


@router.get("/stations", response_model=StationListOut)
async def list_stations(
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> StationListOut:
    """All stations ordered by name, paginated."""
    stops = await StopRepository(session).list_all(limit=limit, offset=offset)
    return StationListOut(
        count=len(stops),
        stations=[StationOut.from_orm_stop(s) for s in stops],
    )


@router.get("/stations/{station_id}", response_model=StationDetailOut)
async def get_station(
    station_id: str,
    session: AsyncSession = Depends(get_session),
) -> StationDetailOut:
    """One station with the routes that serve it."""
    repo = StopRepository(session)
    stop = await repo.get(station_id)
    if stop is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"station '{station_id}' not found",
        )
    routes = await repo.routes_serving(station_id)
    detail = StationDetailOut.model_validate(
        {
            **StationOut.from_orm_stop(stop).model_dump(),
            "routes": [RouteOut.from_orm_route(r).model_dump() for r in routes],
        }
    )
    return detail
