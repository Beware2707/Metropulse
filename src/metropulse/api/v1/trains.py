"""Train endpoints: live fleet snapshot and per-vehicle detail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from metropulse.api.deps import get_train_service
from metropulse.api.schemas import TrainListOut, TrainOut
from metropulse.application.train_service import TrainService

router = APIRouter(tags=["trains"])


@router.get("/trains", response_model=TrainListOut)
async def list_trains(
    service: TrainService = Depends(get_train_service),
) -> TrainListOut:
    """All currently tracked trains, enriched with route and station context."""
    states = await service.list_trains()
    return TrainListOut(count=len(states), trains=[TrainOut.from_domain(s) for s in states])


@router.get("/trains/{vehicle_id}", response_model=TrainOut)
async def get_train(
    vehicle_id: str,
    service: TrainService = Depends(get_train_service),
) -> TrainOut:
    """One tracked train by vehicle ID."""
    state = await service.get_train(vehicle_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"vehicle '{vehicle_id}' is not currently tracked",
        )
    return TrainOut.from_domain(state)
