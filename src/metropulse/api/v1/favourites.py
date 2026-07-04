"""Favourite stations and routes endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_commuter, get_current_user, get_session
from metropulse.api.schemas_commuter import (
    FavouriteRouteOut,
    FavouriteStationIn,
    FavouriteStationOut,
)
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.commuter_models import User
from metropulse.wiring import CommuterServices

router = APIRouter(prefix="/me/favourites", tags=["favourites"])


@router.get("/stations", response_model=list[FavouriteStationOut])
async def list_favourite_stations(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> list[FavouriteStationOut]:
    """The user's favourite stations, ordered by position."""
    rows = await services.favourites.list_stations(session, user.id)
    return [FavouriteStationOut.model_validate(r) for r in rows]


@router.put("/stations/{stop_id}", response_model=FavouriteStationOut)
async def set_favourite_station(
    stop_id: str,
    body: FavouriteStationIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> FavouriteStationOut:
    """Add or update a favourite station."""
    try:
        row = await services.favourites.set_station(
            session, user.id, stop_id, body.label, body.position
        )
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return FavouriteStationOut.model_validate(row)


@router.delete("/stations/{stop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favourite_station(
    stop_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> None:
    """Remove a favourite station."""
    removed = await services.favourites.remove_station(session, user.id, stop_id)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="favourite not found")
    await session.commit()


@router.get("/routes", response_model=list[FavouriteRouteOut])
async def list_favourite_routes(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> list[FavouriteRouteOut]:
    """The user's favourite routes."""
    rows = await services.favourites.list_routes(session, user.id)
    return [FavouriteRouteOut.model_validate(r) for r in rows]


@router.put("/routes/{route_id}", response_model=FavouriteRouteOut)
async def set_favourite_route(
    route_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> FavouriteRouteOut:
    """Add a favourite route (idempotent)."""
    try:
        row = await services.favourites.set_route(session, user.id, route_id)
    except UnknownEntityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return FavouriteRouteOut.model_validate(row)


@router.delete("/routes/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favourite_route(
    route_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    services: CommuterServices = Depends(get_commuter),
) -> None:
    """Remove a favourite route."""
    removed = await services.favourites.remove_route(session, user.id, route_id)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="favourite not found")
    await session.commit()
