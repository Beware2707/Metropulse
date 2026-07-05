"""Worker-side rule engine for commuter automations.

Runs alongside the realtime poller and evaluates, against the live Redis
snapshot:

- destination alerts   -> trigger when ETA to the target drops below threshold
- journey tracking     -> auto-complete on arrival, abandon after a timeout
- last-train reminders -> notify inside the lead window, once per service day

All evaluation is idempotent and crash-safe: state transitions happen inside
one transaction per cycle, and notifications ride the same transaction via
the outbox table.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.commuter.journey_session import JourneySessionTracker
from metropulse.application.commuter.journeys import JourneyService
from metropulse.application.commuter.last_train import LastTrainService
from metropulse.application.commuter.notifications import NotificationService
from metropulse.application.eta_engine import EtaEngine
from metropulse.application.route_resolver import RouteResolver
from metropulse.domain.entities import VehiclePosition, utcnow
from metropulse.domain.events import DestinationReached
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import DestinationAlert
from metropulse.infrastructure.db.commuter_repositories import (
    DestinationAlertRepository,
    JourneyRepository,
    LeaveHomeReminderRepository,
)
from metropulse.infrastructure.redis.event_publisher import RedisDomainEventPublisher
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RuleEvaluationResult:
    """Counters from one realtime evaluation cycle."""

    alerts_triggered: int
    alerts_expired: int
    journeys_completed: int
    journeys_abandoned: int
    interchange_reminders: int = 0
    journeys_missed: int = 0
    delay_notifications: int = 0


class CommuterRuleEngine:
    """Evaluates commuter automations against the live vehicle snapshot."""

    def __init__(
        self,
        store: RedisVehicleStore,
        resolver: RouteResolver,
        eta_engine: EtaEngine,
        session_factory: SessionFactory,
        notifications: NotificationService,
        last_train: LastTrainService,
        journey_service: JourneyService,
        *,
        journey_max_age_hours: float = 6.0,
        delay_notify_seconds: float = 300.0,
        event_publisher: RedisDomainEventPublisher | None = None,
    ) -> None:
        self._store = store
        self._resolver = resolver
        self._eta_engine = eta_engine
        self._session_factory = session_factory
        self._notifications = notifications
        self._last_train = last_train
        self._journeys = journey_service
        self._publisher = event_publisher
        self._sessions = JourneySessionTracker(
            resolver,
            eta_engine,
            journey_service,
            notifications,
            journey_max_age_hours=journey_max_age_hours,
            delay_notify_seconds=delay_notify_seconds,
        )

    async def evaluate_realtime_safe(self) -> RuleEvaluationResult | None:
        """Scheduler entry point: never raises."""
        try:
            return await self.evaluate_realtime()
        except Exception:
            logger.exception("commuter realtime rule evaluation failed")
            return None

    async def evaluate_reminders_safe(self) -> int | None:
        """Scheduler entry point: never raises."""
        try:
            return await self.evaluate_reminders()
        except Exception:
            logger.exception("last-train reminder evaluation failed")
            return None

    async def evaluate_realtime(self) -> RuleEvaluationResult:
        """One evaluation cycle for destination alerts and journeys."""
        snapshot = await self._store.get_all()
        counters = {
            "triggered": 0, "expired": 0, "completed": 0, "abandoned": 0,
            "interchange": 0, "missed": 0, "delay": 0,
        }
        async with self._session_factory() as session:
            async with session.begin():
                for alert in await DestinationAlertRepository(session).list_active():
                    outcome = await self._evaluate_alert(session, alert, snapshot)
                    if outcome in counters:
                        counters[outcome] += 1
                for journey in await JourneyRepository(session).list_active():
                    outcome = await self._sessions.evaluate(session, journey, snapshot)
                    if outcome in counters:
                        counters[outcome] += 1
        result = RuleEvaluationResult(
            alerts_triggered=counters["triggered"],
            alerts_expired=counters["expired"],
            journeys_completed=counters["completed"],
            journeys_abandoned=counters["abandoned"],
            interchange_reminders=counters["interchange"],
            journeys_missed=counters["missed"],
            delay_notifications=counters["delay"],
        )
        if any(counters.values()):
            logger.info(
                "rules: %d alert(s) triggered, %d expired, %d journey(s) completed, "
                "%d abandoned, %d missed, %d interchange reminder(s), %d delay "
                "notification(s)",
                counters["triggered"], counters["expired"], counters["completed"],
                counters["abandoned"], counters["missed"], counters["interchange"],
                counters["delay"],
            )
        return result

    async def _evaluate_alert(
        self,
        session: AsyncSession,
        alert: DestinationAlert,
        snapshot: dict[str, VehiclePosition],
    ) -> str | None:
        vehicle = snapshot.get(alert.vehicle_id)
        if vehicle is None:
            # The train left the feed; the alert can never fire.
            alert.status = "expired"
            return "expired"
        if not vehicle.trip_id:
            return None
        context = await self._resolver.resolve_trip(vehicle.trip_id)
        if context is None:
            return None
        eta = await self._eta_engine.compute(vehicle, context)
        if eta is None:
            return None

        target = next(
            (s for s in eta.stations if s.stop_id == alert.target_stop_id), None
        )
        if target is not None and target.eta_seconds > alert.threshold_seconds:
            return None
        if target is None and not any(
            s.stop_id == alert.target_stop_id for s in context.stops
        ):
            # Target isn't on this trip at all; leave the alert alone rather
            # than firing a wrong notification.
            return None

        alert.status = "triggered"
        alert.triggered_at = utcnow()
        station_name = target.stop_name if target else alert.target_stop_id
        await self._notifications.create(
            session,
            alert.user_id,
            kind="destination_alert",
            title=f"Approaching {station_name}",
            body=f"Your train is about to reach {station_name}. Get ready to alight.",
            payload={
                "alert_id": alert.id,
                "vehicle_id": alert.vehicle_id,
                "stop_id": alert.target_stop_id,
                "eta_seconds": target.eta_seconds if target else 0,
            },
        )
        if self._publisher is not None:
            await self._publisher.publish(
                DestinationReached(
                    user_id=alert.user_id,
                    vehicle_id=alert.vehicle_id,
                    stop_id=alert.target_stop_id,
                    alert_id=alert.id,
                    timestamp=utcnow().isoformat(),
                )
            )
        return "triggered"

    async def evaluate_reminders(self, now: datetime | None = None) -> int:
        """One clock-driven cycle: last-train and leave-home reminders.

        Returns the number of notifications sent. ``now`` is injectable for
        deterministic tests; production runs use the current time.
        """
        now = now or utcnow()
        sent = 0
        async with self._session_factory() as session:
            async with session.begin():
                sent += await self._evaluate_leave_home(session, now)
                due = await self._last_train.due_reminders(session, now)
                for reminder, info in due:
                    reminder.last_notified_service_date = info.service_date
                    minutes_left = max(
                        0, int((info.departure_at - now).total_seconds() // 60)
                    )
                    await self._notifications.create(
                        session,
                        reminder.user_id,
                        kind="last_train",
                        title="Last train reminder",
                        body=(
                            f"The last train from your station leaves in about "
                            f"{minutes_left} minute(s) at "
                            f"{info.departure_at.strftime('%H:%M')}."
                        ),
                        payload={
                            "reminder_id": reminder.id,
                            "stop_id": reminder.stop_id,
                            "route_id": info.route_id,
                            "trip_id": info.trip_id,
                            "departure_at": info.departure_at.isoformat(),
                        },
                    )
                    sent += 1
        if sent:
            logger.info("sent %d reminder notification(s)", sent)
        return sent

    async def _evaluate_leave_home(self, session: AsyncSession, now: datetime) -> int:
        """Fire pending leave-home reminders whose notify time has arrived."""
        sent = 0
        for reminder in await LeaveHomeReminderRepository(session).list_due(now):
            departure = reminder.train_departure_at
            if departure.tzinfo is None:  # SQLite returns naive datetimes
                departure = departure.replace(tzinfo=now.tzinfo)
            minutes_to_leave = reminder.walking_minutes + reminder.buffer_minutes
            await self._notifications.create(
                session,
                reminder.user_id,
                kind="leave_home",
                title="Time to leave",
                body=(
                    f"Leave now to catch your {departure.strftime('%H:%M')} train — "
                    f"about {minutes_to_leave} minute(s) including the walk."
                ),
                payload={
                    "reminder_id": reminder.id,
                    "stop_id": reminder.stop_id,
                    "train_departure_at": departure.isoformat(),
                },
            )
            reminder.status = "sent"
            reminder.sent_at = now
            sent += 1
        return sent
