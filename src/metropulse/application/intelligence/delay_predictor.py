"""Delay estimation from historical travel times.

Compares each completed journey's *actual* duration (``ended_at -
started_at``) against the *scheduled* duration the journey planner would
have quoted for that same trip at that same departure time, for journeys on
the same route within an hour-of-day band. The median delta is the typical
delay for that route/hour.

This is deliberately a system-wide (not per-user) estimate: delay is a
property of the route and time of day, not of any one rider. It is also
deliberately honest about its own limitations — it does not know a journey's
GTFS direction (journeys aren't tagged with one today), and it degrades to
zero-confidence "no delay information yet" rather than guessing when there
isn't enough data. When a real GTFS-Realtime feed becomes available, this
service is the natural place to blend in live-observed delay instead of (or
alongside) this historical estimate — see :class:`TravelTimePredictor` in
``application/ports.py`` for the equivalent seam on the live ETA path.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from statistics import median

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.journey_planner import JourneyPlanner
from metropulse.domain.intelligence import DelayEstimate
from metropulse.infrastructure.db.commuter_repositories import JourneyRepository

logger = logging.getLogger(__name__)

_HOUR_WINDOW = 1
_MIN_SAMPLES_FOR_CONFIDENCE = 10
_MAX_SAMPLE_ROWS = 200
_PLAUSIBLE_MIN_SECONDS = 60.0
_PLAUSIBLE_MAX_SECONDS = 3.0 * 3600.0


class DelayPredictionService:
    """Estimates typical delay for a route around an hour of day."""

    def __init__(self, planner: JourneyPlanner, *, lookback_days: float = 60.0) -> None:
        self._planner = planner
        self._lookback = timedelta(days=lookback_days)

    async def estimate(
        self,
        session: AsyncSession,
        route_id: str,
        direction_id: int | None,
        at: datetime,
    ) -> DelayEstimate:
        """Typical delay (seconds; positive = slower than scheduled) for
        ``route_id`` around ``at``'s hour of day, from real completed trips.

        ``direction_id`` is accepted for API symmetry with the coach/exit
        recommendation endpoints but does not yet filter the sample:
        journeys aren't reliably tagged with a GTFS direction today.
        """
        since = at - self._lookback
        journeys = await JourneyRepository(session).completed_by_route(
            route_id, since=since, limit=_MAX_SAMPLE_ROWS
        )
        in_band = [j for j in journeys if _hour_distance(j.started_at.hour, at.hour) <= _HOUR_WINDOW]

        deltas: list[float] = []
        for journey in in_band:
            if journey.ended_at is None:
                continue
            actual_seconds = (journey.ended_at - journey.started_at).total_seconds()
            if not _PLAUSIBLE_MIN_SECONDS <= actual_seconds <= _PLAUSIBLE_MAX_SECONDS:
                continue
            try:
                plan = await self._planner.plan(
                    journey.origin_stop_id,
                    journey.destination_stop_id,
                    departure_at=journey.started_at,
                )
            except Exception:
                continue
            deltas.append(actual_seconds - plan.expected_travel_seconds)

        sample_size = len(deltas)
        expected_delay = median(deltas) if deltas else 0.0
        confidence = min(1.0, sample_size / _MIN_SAMPLES_FOR_CONFIDENCE)

        return DelayEstimate(
            route_id=route_id,
            direction_id=direction_id,
            hour_of_day=at.hour,
            expected_delay_seconds=round(expected_delay, 1),
            confidence=round(confidence, 3),
            sample_size=sample_size,
        )


def _hour_distance(a: int, b: int) -> int:
    diff = abs(a - b)
    return min(diff, 24 - diff)
