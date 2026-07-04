"""Product analytics: batched event ingestion, summaries, retention."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_repositories import AnalyticsRepository


@dataclass(frozen=True, slots=True)
class IncomingAnalyticsEvent:
    """One client-side analytics event before persistence."""

    event_type: str
    occurred_at: datetime | None = None
    session_id: str | None = None
    payload: dict[str, Any] | None = None


class AnalyticsService:
    """Write-optimized ingestion of raw product events."""

    def __init__(self, max_batch: int = 500) -> None:
        self._max_batch = max_batch

    async def ingest(
        self,
        session: AsyncSession,
        user_id: str | None,
        events: Sequence[IncomingAnalyticsEvent],
    ) -> int:
        """Persist a batch of events; returns the number accepted.

        Raises ``ValueError`` for empty types or oversized batches — clients
        must chunk uploads instead of sending unbounded payloads.
        """
        if len(events) > self._max_batch:
            raise ValueError(f"batch exceeds the maximum of {self._max_batch} events")
        now = utcnow()
        rows = []
        for event in events:
            if not event.event_type.strip():
                raise ValueError("event_type must be non-empty")
            rows.append(
                {
                    "user_id": user_id,
                    "session_id": event.session_id,
                    "event_type": event.event_type.strip(),
                    "occurred_at": event.occurred_at or now,
                    "received_at": now,
                    "payload": event.payload,
                }
            )
        return await AnalyticsRepository(session).add_many(rows)

    async def summary(
        self, session: AsyncSession, since: datetime
    ) -> list[tuple[str, int]]:
        """Event counts by type since a moment (ops/admin view)."""
        return await AnalyticsRepository(session).counts_by_type(since)


async def purge_analytics(session_factory: SessionFactory, retention_days: float) -> int:
    """Delete events past the retention window (periodic worker job)."""
    cutoff = utcnow() - timedelta(days=retention_days)
    async with session_factory() as session:
        async with session.begin():
            return await AnalyticsRepository(session).delete_older_than(cutoff)
