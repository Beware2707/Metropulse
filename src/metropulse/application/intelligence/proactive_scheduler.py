"""Proactive "time to leave" nudges — the worker-side companion to
CommutePredictionService.

The API endpoint (``GET /me/commute-prediction``) is pull-based: a client
has to ask. This service is what makes the same prediction *proactive*: a
periodic worker pass evaluates every user with recent journey history and,
when their predicted departure falls inside a short lead window, fires a
notification through the existing outbox (:class:`NotificationService`) —
the same pipe that already delivers destination alerts, interchange
reminders and last-train reminders. No new delivery mechanism, no new
client polling: the Flutter app's existing notification sync picks this up
exactly like every other notification kind.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.commuter.notifications import NotificationService
from metropulse.application.ports import CommutePredictor
from metropulse.domain.entities import utcnow
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.domain.intelligence import CommutePrediction
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_repositories import (
    JourneyRepository,
    PredictedDepartureNoticeRepository,
)

logger = logging.getLogger(__name__)

# Fallback only for callers that don't pass history_window_days explicitly
# (e.g. ad-hoc scripts/tests). Production wiring (cli.py) passes the SAME
# value as CommutePredictionService's own lookback_days, so the two windows
# can never drift apart from independent config changes.
_DEFAULT_USER_SCAN_WINDOW_DAYS = 90.0


class ProactiveCommuteSchedulerService:
    """Turns learned commute patterns into unprompted "leave now" nudges."""

    def __init__(
        self,
        commute_predictor: CommutePredictor,
        notifications: NotificationService,
        session_factory: SessionFactory,
        *,
        lead_minutes: float = 15.0,
        min_confidence: float = 0.5,
        timezone: str = "Asia/Kolkata",
        history_window_days: float = _DEFAULT_USER_SCAN_WINDOW_DAYS,
    ) -> None:
        self._predictor = commute_predictor
        self._notifications = notifications
        self._session_factory = session_factory
        self._lead_minutes = lead_minutes
        self._min_confidence = min_confidence
        self._tz = ZoneInfo(timezone)
        self._history_window_days = history_window_days

    async def evaluate_safe(self) -> int | None:
        """Scheduler entry point: never raises."""
        try:
            return await self.evaluate()
        except Exception:
            logger.exception("proactive commute scheduler evaluation failed")
            return None

    async def evaluate(self, now: datetime | None = None) -> int:
        """One evaluation cycle; returns the number of nudges sent.

        ``now`` is injectable for deterministic tests; production runs use
        the current time.
        """
        now = now or utcnow()
        sent = 0
        async with self._session_factory() as session:
            async with session.begin():
                journeys = JourneyRepository(session)
                notices = PredictedDepartureNoticeRepository(session)
                user_ids = await journeys.distinct_user_ids_with_history(
                    now - timedelta(days=self._history_window_days)
                )
                for user_id in user_ids:
                    try:
                        prediction = await self._predictor.predict(session, user_id, now)
                    except UnknownEntityError:
                        continue
                    if prediction.confidence < self._min_confidence:
                        continue

                    minutes_until = (
                        prediction.predicted_departure_at - now
                    ).total_seconds() / 60
                    if not (0 <= minutes_until <= self._lead_minutes):
                        continue

                    service_date = prediction.predicted_departure_at.astimezone(self._tz).date()
                    notice = await notices.get(user_id)
                    if notice is not None and notice.last_notified_service_date == service_date:
                        continue

                    await self._notify(session, user_id, prediction, now)
                    await notices.mark_notified(
                        user_id, service_date, prediction.predicted_departure_at, now
                    )
                    sent += 1
        if sent:
            logger.info("sent %d predicted-departure nudge(s)", sent)
        return sent

    async def _notify(
        self,
        session: AsyncSession,
        user_id: str,
        prediction: CommutePrediction,
        now: datetime,
    ) -> None:
        minutes = max(0, round((prediction.predicted_departure_at - now).total_seconds() / 60))
        when = "now" if minutes <= 1 else f"in about {minutes} minute(s)"
        coach_text = (
            f" Coach {prediction.recommended_coach + 1} is your usual pick."
            if prediction.recommended_coach is not None
            else ""
        )
        await self._notifications.create(
            session,
            user_id,
            kind="predicted_departure",
            title="Time to leave soon",
            body=(
                f"You usually leave {when} for {prediction.destination_name}."
                f"{coach_text}"
            ),
            payload={
                "origin_stop_id": prediction.origin_stop_id,
                "destination_stop_id": prediction.destination_stop_id,
                "predicted_departure_at": prediction.predicted_departure_at.isoformat(),
                "confidence": prediction.confidence,
            },
        )
