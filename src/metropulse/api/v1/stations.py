"""Station endpoints: listing and per-station detail with serving routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_session
from metropulse.application.commuter.accessibility_graph import step_free_gate_ids
from metropulse.api.schemas import (
    LastMileRouteOut,
    RouteOut,
    RegionalRailConnectionOut,
    StationAccessibilityOut,
    StationDetailOut,
    StationFacilityOut,
    StationHourlyLoadOut,
    StationListOut,
    StationOut,
    StationTopDestinationsOut,
)
from metropulse.infrastructure.db.commuter_repositories import (
    LastMileRouteRepository,
    RegionalRailConnectionRepository,
    StationAccessibilityRepository,
    StationFacilityRepository,
    StationHourlyLoadRepository,
    StationTopDestinationsRepository,
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


@router.get(
    "/stations/{station_id}/accessibility", response_model=StationAccessibilityOut
)
async def get_station_accessibility(
    station_id: str,
    session: AsyncSession = Depends(get_session),
) -> StationAccessibilityOut:
    """Step-free gate->lift->platform graph for one station.

    404 means the DMRC pathways dataset does not cover this station — the
    client must say "no accessibility data", not infer inaccessibility.
    """
    row = await StationAccessibilityRepository(session).get(station_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no accessibility data curated for this station",
        )
    out = StationAccessibilityOut.model_validate(row)
    qualified = step_free_gate_ids(
        row.gates or [], row.lifts or [], row.platforms or [], row.edges or []
    )
    out.step_free_gates = [g for g in (row.gates or []) if str(g.get("id")) in qualified]
    return out


@router.get("/stations/{station_id}/busyness", response_model=StationHourlyLoadOut)
async def get_station_busyness(
    station_id: str,
    session: AsyncSession = Depends(get_session),
) -> StationHourlyLoadOut:
    """Typical hourly entry/exit profile for one station (dated snapshot)."""
    row = await StationHourlyLoadRepository(session).get(station_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no ridership profile curated for this station",
        )
    return StationHourlyLoadOut.model_validate(row)


@router.get(
    "/stations/{station_id}/top-destinations",
    response_model=StationTopDestinationsOut,
)
async def get_station_top_destinations(
    station_id: str,
    session: AsyncSession = Depends(get_session),
) -> StationTopDestinationsOut:
    """Where riders from this origin actually went (DMRC OD matrix month)."""
    row = await StationTopDestinationsRepository(session).get(station_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no destination data curated for this station",
        )
    return StationTopDestinationsOut.model_validate(row)


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


@router.get(
    "/stations/{station_id}/regional-rail",
    response_model=list[RegionalRailConnectionOut],
)
async def get_station_regional_rail(
    station_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[RegionalRailConnectionOut]:
    """Walkable Namo Bharat (RRTS) connections from this metro station.

    An empty list is the normal answer for almost every station -- only
    stations NCRTC actually runs trips near have one. RRTS is a different
    operator with its own fares; this is a connection, not a metro route.
    """
    rows = await RegionalRailConnectionRepository(session).for_station(station_id)
    return [RegionalRailConnectionOut.model_validate(r) for r in rows]
