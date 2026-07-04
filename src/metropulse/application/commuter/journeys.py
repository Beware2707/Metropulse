"""Journey tracking: a user's live trip from origin to destination."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.domain.entities import utcnow
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.commuter_models import Journey, JourneyEvent
from metropulse.infrastructure.db.commuter_repositories import JourneyRepository
from metropulse.infrastructure.db.repositories import StopRepository


class JourneyService:
    """Lifecycle management for tracked journeys.

    A user has at most one active journey; starting a new one supersedes the
    previous. All transitions are logged to ``journey_events`` — that stream
    is both the product history and future ML training data.
    """

    async def start(
        self,
        session: AsyncSession,
        user_id: str,
        origin_stop_id: str,
        destination_stop_id: str,
        vehicle_id: str | None = None,
        route_id: str | None = None,
        trip_id: str | None = None,
        interchange_stop_ids: Sequence[str] = (),
    ) -> Journey:
        """Start a journey, superseding any active one.

        ``interchange_stop_ids`` (usually taken from a journey plan) makes
        the worker raise interchange reminders as the train approaches each
        of those stations.

        Raises :class:`UnknownEntityError` for unknown stops and
        ``ValueError`` when origin equals destination.
        """
        if origin_stop_id == destination_stop_id:
            raise ValueError("origin and destination must differ")
        stops = StopRepository(session)
        for stop_id in (origin_stop_id, destination_stop_id, *interchange_stop_ids):
            if await stops.get(stop_id) is None:
                raise UnknownEntityError(f"stop '{stop_id}' not found")

        repo = JourneyRepository(session)
        now = utcnow()
        existing = await repo.active_for_user(user_id)
        if existing is not None:
            existing.status = "abandoned"
            existing.ended_at = now
            repo.add_event(_event(existing.id, "superseded", now))

        journey = Journey(
            user_id=user_id,
            origin_stop_id=origin_stop_id,
            destination_stop_id=destination_stop_id,
            route_id=route_id,
            vehicle_id=vehicle_id,
            trip_id=trip_id,
            status="active",
            started_at=now,
            payload=(
                {"interchange_stop_ids": list(interchange_stop_ids)}
                if interchange_stop_ids
                else None
            ),
        )
        repo.add(journey)
        await session.flush()
        repo.add_event(_event(journey.id, "started", now, {"vehicle_id": vehicle_id}))
        return journey

    async def current(self, session: AsyncSession, user_id: str) -> Journey | None:
        """The user's active journey, if any."""
        return await JourneyRepository(session).active_for_user(user_id)

    async def history(
        self, session: AsyncSession, user_id: str, limit: int = 50
    ) -> Sequence[Journey]:
        """The user's journeys, newest first."""
        return await JourneyRepository(session).history_for_user(user_id, limit)

    async def complete(
        self, session: AsyncSession, user_id: str, journey_id: int, *, auto: bool = False
    ) -> Journey | None:
        """Complete an active journey owned by the user (None if no match)."""
        return await self._finish(session, user_id, journey_id, "completed", auto=auto)

    async def abandon(
        self, session: AsyncSession, user_id: str, journey_id: int
    ) -> Journey | None:
        """Abandon an active journey owned by the user (None if no match)."""
        return await self._finish(session, user_id, journey_id, "abandoned", auto=False)

    async def _finish(
        self,
        session: AsyncSession,
        user_id: str,
        journey_id: int,
        status: str,
        *,
        auto: bool,
    ) -> Journey | None:
        repo = JourneyRepository(session)
        journey = await repo.get(journey_id)
        if journey is None or journey.user_id != user_id or journey.status != "active":
            return None
        now = utcnow()
        journey.status = status
        journey.ended_at = now
        repo.add_event(_event(journey.id, status, now, {"auto": auto}))
        return journey


def _event(
    journey_id: int,
    event_type: str,
    occurred_at: datetime,
    payload: dict[str, Any] | None = None,
) -> JourneyEvent:
    return JourneyEvent(
        journey_id=journey_id,
        event_type=event_type,
        occurred_at=occurred_at,
        payload=payload,
    )
