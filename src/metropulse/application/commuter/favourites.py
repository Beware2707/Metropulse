"""Favourite stations and routes."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.domain.entities import utcnow
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.commuter_models import FavouriteRoute, FavouriteStation
from metropulse.infrastructure.db.commuter_repositories import FavouriteRepository
from metropulse.infrastructure.db.repositories import RouteRepository, StopRepository


class FavouritesService:
    """Upsert-style management of a user's favourite stations and routes."""

    async def set_station(
        self,
        session: AsyncSession,
        user_id: str,
        stop_id: str,
        label: str | None,
        position: int,
    ) -> FavouriteStation:
        """Add or update a favourite station.

        Raises :class:`UnknownEntityError` when the stop doesn't exist.
        """
        if await StopRepository(session).get(stop_id) is None:
            raise UnknownEntityError(f"stop '{stop_id}' not found")
        repo = FavouriteRepository(session)
        existing = await repo.get_station(user_id, stop_id)
        if existing is not None:
            existing.label = label
            existing.position = position
            return existing
        favourite = FavouriteStation(
            user_id=user_id,
            stop_id=stop_id,
            label=label,
            position=position,
            created_at=utcnow(),
        )
        repo.add(favourite)
        await session.flush()
        return favourite

    async def list_stations(
        self, session: AsyncSession, user_id: str
    ) -> Sequence[FavouriteStation]:
        """The user's favourite stations, ordered by position."""
        return await FavouriteRepository(session).stations_for(user_id)

    async def remove_station(
        self, session: AsyncSession, user_id: str, stop_id: str
    ) -> bool:
        """Remove a favourite station; returns whether it existed."""
        return await FavouriteRepository(session).remove_station(user_id, stop_id)

    async def set_route(
        self, session: AsyncSession, user_id: str, route_id: str
    ) -> FavouriteRoute:
        """Add a favourite route (idempotent).

        Raises :class:`UnknownEntityError` when the route doesn't exist.
        """
        if await RouteRepository(session).get(route_id) is None:
            raise UnknownEntityError(f"route '{route_id}' not found")
        repo = FavouriteRepository(session)
        existing = await repo.get_route(user_id, route_id)
        if existing is not None:
            return existing
        favourite = FavouriteRoute(user_id=user_id, route_id=route_id, created_at=utcnow())
        repo.add(favourite)
        await session.flush()
        return favourite

    async def list_routes(
        self, session: AsyncSession, user_id: str
    ) -> Sequence[FavouriteRoute]:
        """The user's favourite routes."""
        return await FavouriteRepository(session).routes_for(user_id)

    async def remove_route(
        self, session: AsyncSession, user_id: str, route_id: str
    ) -> bool:
        """Remove a favourite route; returns whether it existed."""
        return await FavouriteRepository(session).remove_route(user_id, route_id)
