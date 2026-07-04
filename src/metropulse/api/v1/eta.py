"""ETA endpoint: per-station arrival estimates for one vehicle."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from metropulse.api.deps import get_eta_engine, get_resolver, get_vehicle_store
from metropulse.api.schemas import VehicleEtaOut
from metropulse.application.eta_engine import EtaEngine
from metropulse.application.route_resolver import RouteResolver
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore

router = APIRouter(tags=["eta"])


@router.get("/eta/{vehicle_id}", response_model=VehicleEtaOut)
async def get_eta(
    vehicle_id: str,
    store: RedisVehicleStore = Depends(get_vehicle_store),
    resolver: RouteResolver = Depends(get_resolver),
    engine: EtaEngine = Depends(get_eta_engine),
) -> VehicleEtaOut:
    """ETAs to every remaining station on the vehicle's current trip."""
    vehicle = await store.get(vehicle_id)
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"vehicle '{vehicle_id}' is not currently tracked",
        )
    if not vehicle.trip_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="vehicle is not reporting a trip; ETA unavailable",
        )
    context = await resolver.resolve_trip(vehicle.trip_id)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"realtime trip '{vehicle.trip_id}' cannot be matched to static GTFS",
        )
    eta = await engine.compute(vehicle, context)
    if eta is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="trip has no usable stop sequence; ETA unavailable",
        )
    return VehicleEtaOut.from_domain(eta)
