"""Coach recommendation engine.

Architecture: the recommendation service is a pure ranking function over two
signals — per-coach crowding (from a :class:`CrowdPredictor` port) and exit
alignment at the destination (from curated coach-exit hints). The shipped
predictor aggregates historical ``crowd_observations``; an ML model later
implements the same port (and/or writes ``source='model'`` observations)
without touching this service, the API, or the schema.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.domain.commuter import CoachRecommendation, CoachScore, CrowdForecast
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_repositories import (
    CrowdObservationRepository,
    StationExitRepository,
)
from metropulse.infrastructure.db.repositories import StopRepository

logger = logging.getLogger(__name__)

_MIN_SAMPLES_PER_COACH = 3


class HistoricalCrowdPredictor:
    """CrowdPredictor implementation over historical observations.

    Averages recent observations for the same route/direction in a matching
    hour-of-day band; coaches with too little data fall back to a triangular
    prior (middle coaches run fuller — a well-documented metro pattern).
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        lookback_days: int = 28,
        hour_window: int = 1,
    ) -> None:
        self._session_factory = session_factory
        self._lookback = timedelta(days=lookback_days)
        self._hour_window = hour_window

    async def coach_occupancy(
        self,
        route_id: str | None,
        direction_id: int | None,
        at: datetime,
        coach_count: int,
    ) -> CrowdForecast:
        """Per-coach occupancy from observations, prior-backed where sparse."""
        async with self._session_factory() as session:
            observations = await CrowdObservationRepository(session).recent(
                route_id, direction_id, since=at - self._lookback
            )

        per_coach: dict[int, list[float]] = {}
        for obs in observations:
            if obs.coach_index is None or not 0 <= obs.coach_index < coach_count:
                continue
            if _hour_distance(obs.observed_at.hour, at.hour) > self._hour_window:
                continue
            per_coach.setdefault(obs.coach_index, []).append(obs.occupancy)

        prior = _triangular_prior(coach_count)
        occupancies: list[float] = []
        samples_used = 0
        observed_any = False
        for index in range(coach_count):
            samples = per_coach.get(index, [])
            if len(samples) >= _MIN_SAMPLES_PER_COACH:
                occupancies.append(min(max(sum(samples) / len(samples), 0.0), 1.0))
                samples_used += len(samples)
                observed_any = True
            else:
                occupancies.append(prior[index])
        return CrowdForecast(
            occupancies=tuple(occupancies),
            source="observed" if observed_any else "prior",
            model_version=None,
            sample_count=samples_used,
        )


class CoachRecommendationService:
    """Ranks coaches by (low crowding, exit alignment at destination)."""

    def __init__(
        self,
        predictor: HistoricalCrowdPredictor,
        *,
        default_coach_count: int = 8,
        crowd_weight: float = 0.6,
        exit_weight: float = 0.4,
    ) -> None:
        self._predictor = predictor
        self._default_coach_count = default_coach_count
        self._crowd_weight = crowd_weight
        self._exit_weight = exit_weight

    async def recommend(
        self,
        session: AsyncSession,
        origin_stop_id: str,
        destination_stop_id: str,
        route_id: str | None,
        direction_id: int | None,
        at: datetime,
    ) -> CoachRecommendation:
        """Ranked coach choices for a journey.

        Raises :class:`UnknownEntityError` for unknown stops.
        """
        stops = StopRepository(session)
        for stop_id in (origin_stop_id, destination_stop_id):
            if await stops.get(stop_id) is None:
                raise UnknownEntityError(f"stop '{stop_id}' not found")

        hints = await StationExitRepository(session).hints_for(
            destination_stop_id, route_id=route_id, direction_id=direction_id
        )
        hint_coaches = sorted({h.coach_index for h in hints if h.coach_index >= 0})
        coach_count = self._default_coach_count
        if hint_coaches:
            coach_count = max(coach_count, hint_coaches[-1] + 1)

        forecast = await self._predictor.coach_occupancy(
            route_id, direction_id, at, coach_count
        )

        scores = [
            self._score_coach(index, forecast, hint_coaches, coach_count)
            for index in range(coach_count)
        ]
        ranked = tuple(sorted(scores, key=lambda s: (-s.score, s.coach_index)))
        return CoachRecommendation(
            origin_stop_id=origin_stop_id,
            destination_stop_id=destination_stop_id,
            coach_count=coach_count,
            crowd_source=forecast.source,
            model_version=forecast.model_version,
            recommended_coach=ranked[0].coach_index,
            coaches=ranked,
        )

    def _score_coach(
        self,
        index: int,
        forecast: CrowdForecast,
        hint_coaches: list[int],
        coach_count: int,
    ) -> CoachScore:
        occupancy = forecast.occupancies[index]
        if hint_coaches:
            distance = min(abs(index - hint) for hint in hint_coaches)
            alignment = 1.0 - distance / max(coach_count - 1, 1)
        else:
            alignment = 0.5  # no exit data: neutral, crowding decides

        score = self._crowd_weight * (1.0 - occupancy) + self._exit_weight * alignment
        reasons: list[str] = []
        if occupancy <= 0.45:
            reasons.append("typically less crowded")
        elif occupancy >= 0.7:
            reasons.append("typically crowded")
        if hint_coaches and index in hint_coaches:
            reasons.append("stops nearest to a destination exit")
        elif hint_coaches and alignment >= 0.75:
            reasons.append("short walk to a destination exit")
        return CoachScore(
            coach_index=index,
            occupancy=round(occupancy, 3),
            exit_alignment=round(alignment, 3),
            score=round(score, 4),
            reasons=tuple(reasons),
        )


def _hour_distance(a: int, b: int) -> int:
    """Circular distance between two hours of day."""
    diff = abs(a - b)
    return min(diff, 24 - diff)


def _triangular_prior(coach_count: int) -> list[float]:
    """Prior occupancy: fullest at the centre, lighter at both ends."""
    if coach_count == 1:
        return [0.6]
    centre = (coach_count - 1) / 2.0
    return [
        0.4 + 0.35 * (1.0 - abs(index - centre) / centre) if centre > 0 else 0.6
        for index in range(coach_count)
    ]
