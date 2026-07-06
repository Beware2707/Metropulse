"""Journey session tracking: the live lifecycle of a commuter's trip.

    start -> track train -> interchange reminder -> arrive (or miss) -> end

Evaluated by the worker against every feed update. One outcome per journey
per cycle, in priority order:

  abandoned   session timed out (no activity within the max age)
  completed   the tracked train reached the destination
  missed      the tracked train passed the destination without arriving
  interchange the train is approaching a planned interchange station
  delay       the tracked train is running late beyond the notify threshold

Each outcome writes the notification inside the caller's transaction (outbox
semantics) and emits a domain event best-effort.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.commuter.journeys import JourneyService
from metropulse.application.commuter.notifications import NotificationService
from metropulse.application.eta_engine import EtaEngine
from metropulse.application.route_resolver import RouteResolver
from metropulse.domain.entities import (
    TrainLocation,
    TripContext,
    VehiclePosition,
    utcnow,
)
from metropulse.infrastructure.db.commuter_models import Journey

logger = logging.getLogger(__name__)


class JourneySessionTracker:
    """Evaluates one active journey against the live vehicle snapshot."""

    def __init__(
        self,
        resolver: RouteResolver,
        eta_engine: EtaEngine,
        journeys: JourneyService,
        notifications: NotificationService,
        *,
        journey_max_age_hours: float = 6.0,
        delay_notify_seconds: float = 300.0,
    ) -> None:
        self._resolver = resolver
        self._eta_engine = eta_engine
        self._journeys = journeys
        self._notifications = notifications
        self._max_age = timedelta(hours=journey_max_age_hours)
        self._delay_notify_seconds = delay_notify_seconds

    async def evaluate(
        self,
        session: AsyncSession,
        journey: Journey,
        snapshot: dict[str, VehiclePosition],
    ) -> str | None:
        """Advance one journey session; returns the outcome or None."""
        now = utcnow()
        started = journey.started_at
        if started.tzinfo is None:  # SQLite returns naive datetimes
            started = started.replace(tzinfo=now.tzinfo)
        if now - started > self._max_age:
            finished = await self._journeys.abandon(session, journey.user_id, journey.id)
            return "abandoned" if finished else None

        if not journey.vehicle_id:
            return None
        vehicle = snapshot.get(journey.vehicle_id)
        if vehicle is None or not vehicle.trip_id:
            return None
        context = await self._resolver.resolve_trip(vehicle.trip_id)
        if context is None:
            return None
        location = self._resolver.locate(vehicle, context)
        current = location.current_station
        if current is None:
            return None

        if current.stop_id == journey.destination_stop_id:
            return await self._complete(session, journey, current.name)

        if self._has_passed_destination(journey, context, current.sequence):
            return await self._missed(session, journey)

        interchange = await self._maybe_remind_interchange(session, journey, location)
        if interchange is not None:
            return interchange

        return await self._maybe_notify_delay(session, journey, vehicle, context)

    async def _complete(
        self, session: AsyncSession, journey: Journey, station_name: str
    ) -> str | None:
        finished = await self._journeys.complete(
            session, journey.user_id, journey.id, auto=True
        )
        if finished is None:
            return None
        await self._notifications.create(
            session,
            journey.user_id,
            kind="journey_completed",
            title="🎉 You're here!",
            body=f"You've reached {station_name}. Have a great day!",
            payload={"journey_id": journey.id, "stop_id": journey.destination_stop_id},
        )
        return "completed"

    def _has_passed_destination(
        self, journey: Journey, context: TripContext, current_sequence: int
    ) -> bool:
        """True when the train is beyond the destination on this trip."""
        destination_sequence = next(
            (
                stop.sequence
                for stop in context.stops
                if stop.stop_id == journey.destination_stop_id
            ),
            None,
        )
        return destination_sequence is not None and current_sequence > destination_sequence

    async def _missed(self, session: AsyncSession, journey: Journey) -> str | None:
        finished = await self._journeys.mark_missed(session, journey.user_id, journey.id)
        if finished is None:
            return None
        await self._notifications.create(
            session,
            journey.user_id,
            kind="missed_stop",
            title="You missed your stop",
            body=(
                "Your train has passed your destination. Alight at the next "
                "station and take a train back."
            ),
            payload={"journey_id": journey.id, "stop_id": journey.destination_stop_id},
        )
        return "missed"

    async def _maybe_remind_interchange(
        self, session: AsyncSession, journey: Journey, location: TrainLocation
    ) -> str | None:
        """Notify once per planned interchange as the train approaches it."""
        payload = journey.payload or {}
        planned: list[str] = payload.get("interchange_stop_ids") or []
        notified: list[str] = payload.get("notified_interchanges") or []
        next_station = location.next_station
        if (
            next_station is None
            or next_station.stop_id not in planned
            or next_station.stop_id in notified
        ):
            return None
        await self._notifications.create(
            session,
            journey.user_id,
            kind="interchange_reminder",
            title=f"Interchange ahead: {next_station.name}",
            body=f"Get ready to change trains at {next_station.name}, the next station.",
            payload={"journey_id": journey.id, "stop_id": next_station.stop_id},
        )
        # Reassign (not mutate) so SQLAlchemy detects the JSON change.
        journey.payload = {
            **payload,
            "notified_interchanges": [*notified, next_station.stop_id],
        }
        return "interchange"

    async def _maybe_notify_delay(
        self,
        session: AsyncSession,
        journey: Journey,
        vehicle: VehiclePosition,
        context: TripContext,
    ) -> str | None:
        """Notify once per journey when the tracked train runs badly late."""
        payload = journey.payload or {}
        if payload.get("delay_notified"):
            return None
        eta = await self._eta_engine.compute(vehicle, context)
        if eta is None or eta.delay_seconds is None:
            return None
        if eta.delay_seconds < self._delay_notify_seconds:
            return None
        minutes = int(eta.delay_seconds // 60)
        await self._notifications.create(
            session,
            journey.user_id,
            kind="journey_delay",
            title="Your train is running late",
            body=f"Your train is running about {minutes} minute(s) behind schedule.",
            payload={"journey_id": journey.id, "delay_seconds": eta.delay_seconds},
        )
        journey.payload = {**payload, "delay_notified": True}
        return "delay"
