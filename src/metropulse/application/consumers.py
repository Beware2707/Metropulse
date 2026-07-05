"""Event consumers for the feed-update stream.

These implement the fan-out stage of the event-driven pipeline:

    GTFS feed -> ingestion worker -> Redis stream -> { ETA | notify | analytics }
                                                   -> WebSocket gateways

Each consumer runs in its own consumer group, so all of them see every
update event independently and can fail/restart without affecting the rest.
"""

from __future__ import annotations

import logging
from typing import Any

from metropulse.application.eta_service import CachedEtaService
from metropulse.application.route_resolver import RouteResolver
from metropulse.domain.entities import VehiclePosition, utcnow
from metropulse.domain.events import EtaUpdated
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_repositories import AnalyticsRepository
from metropulse.infrastructure.redis.event_publisher import RedisDomainEventPublisher

logger = logging.getLogger(__name__)


class EtaWarmer:
    """Precomputes ETAs for changed vehicles, warming the Redis ETA cache.

    API replicas then serve ``GET /eta/{vehicleId}`` as pure cache hits for
    every tracked train until its next position update.
    """

    def __init__(
        self,
        resolver: RouteResolver,
        eta_service: CachedEtaService,
        event_publisher: RedisDomainEventPublisher | None = None,
    ) -> None:
        self._resolver = resolver
        self._eta_service = eta_service
        self._events = event_publisher

    async def handle(self, event: dict[str, Any]) -> None:
        """Compute (and thereby cache) ETAs for each changed train."""
        if event.get("type") != "update":
            return
        for train in [*event.get("added", []), *event.get("moved", [])]:
            vehicle_data = train.get("vehicle")
            if not vehicle_data:
                continue
            vehicle = VehiclePosition.from_dict(vehicle_data)
            if not vehicle.trip_id:
                continue
            context = await self._resolver.resolve_trip(vehicle.trip_id)
            if context is None:
                continue
            eta = await self._eta_service.compute(vehicle, context)
            if eta is not None and self._events is not None:
                await self._events.publish(
                    EtaUpdated(
                        vehicle_id=eta.vehicle_id,
                        trip_id=eta.trip_id,
                        next_stop_id=eta.next_station.stop_id if eta.next_station else None,
                        eta_seconds=eta.next_station.eta_seconds if eta.next_station else None,
                        delay_seconds=eta.delay_seconds,
                        timestamp=eta.computed_at.isoformat(),
                    )
                )


class FeedAnalyticsRecorder:
    """Persists per-poll feed telemetry as system analytics events.

    These rows power ops dashboards (fleet size over time, feed gaps) and
    are training data for future demand/crowding models — no schema beyond
    the existing analytics table is needed.
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def handle(self, event: dict[str, Any]) -> None:
        """Record one 'feed_update' analytics event per stream update."""
        if event.get("type") != "update":
            return
        now = utcnow()
        row = {
            "user_id": None,
            "session_id": None,
            "event_type": "feed_update",
            "occurred_at": now,
            "received_at": now,
            "payload": {
                "seq": event.get("seq"),
                "added": len(event.get("added", [])),
                "moved": len(event.get("moved", [])),
                "removed": len(event.get("removed", [])),
                "stale": len(event.get("stale", [])),
                "ts": event.get("ts"),
            },
        }
        async with self._session_factory() as session:
            async with session.begin():
                await AnalyticsRepository(session).add_many([row])
