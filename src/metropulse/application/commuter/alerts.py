"""Destination alerts (per-user, realtime-evaluated) and service alerts."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Awaitable, Callable, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.domain.entities import utcnow
from metropulse.domain.exceptions import NotTrackedError, UnknownEntityError
from metropulse.infrastructure.db.commuter_models import DestinationAlert, ServiceAlert
from metropulse.infrastructure.db.commuter_repositories import (
    DestinationAlertRepository,
    ServiceAlertRepository,
)
from metropulse.infrastructure.db.repositories import StopRepository
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore

SEVERITIES = ("info", "warning", "severe")


class DestinationAlertService:
    """CRUD for 'tell me when my train nears station X' alerts.

    Evaluation happens in the worker's rule engine; this service only manages
    the alert lifecycle from the API side.
    """

    def __init__(self, store: RedisVehicleStore) -> None:
        self._store = store

    async def create(
        self,
        session: AsyncSession,
        user_id: str,
        vehicle_id: str,
        target_stop_id: str,
        threshold_seconds: int,
    ) -> DestinationAlert:
        """Create an active alert.

        Raises :class:`UnknownEntityError` for an unknown stop and
        :class:`NotTrackedError` when the vehicle isn't in the live snapshot —
        an alert on an untracked train would silently never fire.
        """
        if await StopRepository(session).get(target_stop_id) is None:
            raise UnknownEntityError(f"stop '{target_stop_id}' not found")
        if await self._store.get(vehicle_id) is None:
            raise NotTrackedError(f"vehicle '{vehicle_id}' is not currently tracked")
        alert = DestinationAlert(
            user_id=user_id,
            vehicle_id=vehicle_id,
            target_stop_id=target_stop_id,
            threshold_seconds=threshold_seconds,
            status="active",
            created_at=utcnow(),
        )
        DestinationAlertRepository(session).add(alert)
        await session.flush()
        return alert

    async def list_for_user(
        self, session: AsyncSession, user_id: str
    ) -> Sequence[DestinationAlert]:
        """The user's alerts, newest first."""
        return await DestinationAlertRepository(session).list_for_user(user_id)

    async def cancel(self, session: AsyncSession, user_id: str, alert_id: int) -> bool:
        """Cancel one of the user's active alerts; returns whether it matched."""
        alert = await DestinationAlertRepository(session).get(alert_id)
        if alert is None or alert.user_id != user_id or alert.status != "active":
            return False
        alert.status = "cancelled"
        return True


class ServiceAlertService:
    """Admin-managed (and later feed-ingested) service disruption alerts."""

    def __init__(self, publish: Callable[[str], Awaitable[None]] | None = None) -> None:
        # Optional realtime fan-out: alerts are pushed to WebSocket clients
        # through the same channel the vehicle diffs use.
        self._publish = publish

    async def create(
        self,
        session: AsyncSession,
        *,
        title: str,
        description: str,
        severity: str,
        route_id: str | None = None,
        stop_id: str | None = None,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        source: str = "admin",
    ) -> ServiceAlert:
        """Create and broadcast a service alert.

        Raises ``ValueError`` for an unknown severity.
        """
        if severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}")
        now = utcnow()
        alert = ServiceAlert(
            source=source,
            severity=severity,
            title=title,
            description=description,
            route_id=route_id,
            stop_id=stop_id,
            starts_at=starts_at or now,
            ends_at=ends_at,
            created_at=now,
            updated_at=now,
        )
        ServiceAlertRepository(session).add(alert)
        await session.flush()
        if self._publish is not None:
            await self._publish(
                json.dumps({"type": "alert", "ts": now.isoformat(), "alert": to_dict(alert)})
            )
        return alert

    async def revoke(self, session: AsyncSession, alert_id: int) -> bool:
        """Revoke an alert; returns whether it existed and was active."""
        alert = await ServiceAlertRepository(session).get(alert_id)
        if alert is None or alert.revoked_at is not None:
            return False
        now = utcnow()
        alert.revoked_at = now
        alert.updated_at = now
        return True

    async def list_active(
        self,
        session: AsyncSession,
        now: datetime | None = None,
        route_id: str | None = None,
        stop_id: str | None = None,
    ) -> Sequence[ServiceAlert]:
        """Alerts currently in effect, optionally scoped to a route/stop."""
        return await ServiceAlertRepository(session).list_active(
            now or utcnow(), route_id=route_id, stop_id=stop_id
        )


def to_dict(alert: ServiceAlert) -> dict[str, Any]:
    """JSON-compatible representation used in WS frames."""
    return {
        "id": alert.id,
        "source": alert.source,
        "severity": alert.severity,
        "title": alert.title,
        "description": alert.description,
        "route_id": alert.route_id,
        "stop_id": alert.stop_id,
        "starts_at": alert.starts_at.isoformat(),
        "ends_at": alert.ends_at.isoformat() if alert.ends_at else None,
    }
