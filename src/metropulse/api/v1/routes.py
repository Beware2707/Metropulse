"""Route endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.api.deps import get_session
from metropulse.api.schemas import RouteListOut, RouteOut
from metropulse.infrastructure.db.repositories import RouteRepository

router = APIRouter(tags=["routes"])


@router.get("/routes", response_model=RouteListOut)
async def list_routes(
    session: AsyncSession = Depends(get_session),
) -> RouteListOut:
    """All routes in the static GTFS dataset."""
    routes = await RouteRepository(session).list_all()
    return RouteListOut(count=len(routes), routes=[RouteOut.from_orm_route(r) for r in routes])
