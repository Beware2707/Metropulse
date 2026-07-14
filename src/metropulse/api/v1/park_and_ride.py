"""Park & ride endpoint: parking stations ranked by drive + metro cost.

Schemas live here to stay conflict-free with parallel schema-file work.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_commuter, get_session
from metropulse.application.commuter.park_and_ride import ParkAndRideService
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.wiring import CommuterServices

router = APIRouter(tags=["park-and-ride"])


class ParkAndRideCandidateOut(BaseModel):
    """A parking station scored for a drive-then-ride trip."""

    stop_id: str
    name: str
    distance_km: float
    car_capacity: int | None
    motorcycle_capacity: int | None
    cycle_capacity: int | None
    operator: str | None
    contact: str | None
    parking_lat: float | None
    parking_lon: float | None
    metro_minutes: int | None
    metro_summary: str | None


class ParkAndRideOut(BaseModel):
    """Ranked parking stations for a destination."""

    destination: str
    candidates: list[ParkAndRideCandidateOut]


@router.get("/park-and-ride", response_model=ParkAndRideOut)
async def park_and_ride(
    destination: str,
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> ParkAndRideOut:
    """Parking stations near you, ranked by straight-line drive + metro time.

    Distances are straight-line to the station, and capacities are
    DMRC-published totals (not live availability). 404 for an unknown
    destination.
    """
    service = ParkAndRideService(services.planner)
    try:
        candidates = await service.candidates(session, destination, lat, lon)
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ParkAndRideOut(
        destination=destination,
        candidates=[
            ParkAndRideCandidateOut(
                stop_id=c.stop_id,
                name=c.name,
                distance_km=c.distance_km,
                car_capacity=c.car_capacity,
                motorcycle_capacity=c.motorcycle_capacity,
                cycle_capacity=c.cycle_capacity,
                operator=c.operator,
                contact=c.contact,
                parking_lat=c.parking_lat,
                parking_lon=c.parking_lon,
                metro_minutes=c.metro_minutes,
                metro_summary=c.metro_summary,
            )
            for c in candidates
        ],
    )
