"""Station endpoints: listing and per-station detail with serving routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_session
from metropulse.api.schemas import (
    LastMileRouteOut,
    RouteOut,
    StationDetailOut,
    StationFacilityOut,
    StationListOut,
    StationOut,
)
from metropulse.infrastructure.db.commuter_repositories import (
    LastMileRouteRepository,
    StationFacilityRepository,
)
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


class StationFacilitySummaryOut(BaseModel):
    """Compact per-station facility flags for whole-network consumers."""

    facilities: dict[str, dict[str, bool | None]]


@router.get("/stations/facilities/summary", response_model=StationFacilitySummaryOut)
async def facilities_summary(
    session: AsyncSession = Depends(get_session),
) -> StationFacilitySummaryOut:
    """Elevated/underground flag for every curated station, in one call.

    Powers whole-route computations (e.g. 'what share of your ride is
    underground') without a request per station. ``elevated`` is null where
    the source data didn't specify it.
    """
    rows = await StationFacilityRepository(session).all_rows()
    return StationFacilitySummaryOut(
        facilities={row.stop_id: {"elevated": row.elevated} for row in rows}
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


@router.get("/stations/{station_id}/facilities", response_model=StationFacilityOut)
async def get_station_facilities(
    station_id: str,
    session: AsyncSession = Depends(get_session),
) -> StationFacilityOut:
    """Curated accessibility + parking facilities for one station."""
    facility = await StationFacilityRepository(session).get(station_id)
    if facility is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no facility data curated for this station",
        )
    return StationFacilityOut.model_validate(facility)


@router.get("/stations/{station_id}/last-mile", response_model=list[LastMileRouteOut])
async def get_station_last_mile(
    station_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[LastMileRouteOut]:
    """Curated shared-mobility (e-rickshaw) last-mile routes hubbed at a
    station. Unlike /facilities, an empty list (not a 404) is the normal
    response when no last-mile options are curated for this station."""
    routes = await LastMileRouteRepository(session).for_station(station_id)
    return [LastMileRouteOut.model_validate(route) for route in routes]
