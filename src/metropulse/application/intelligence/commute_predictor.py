"""Commute prediction: learns a user's likely next trip from their own
journey history.

Deliberately not a black box: journeys are bucketed by day-type (weekday vs.
weekend) and grouped by (origin, destination), and the most-travelled pair
whose typical departure time is closest to right now is predicted. Confidence
scales with sample size (``sample_size / _MIN_SAMPLES_FOR_CONFIDENCE``,
capped at 1.0) so a prediction from two trips never looks as certain as one
from twenty.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.commuter.coach import CoachRecommendationService
from metropulse.application.commuter.exits import ExitService
from metropulse.application.journey_planner import JourneyPlanner
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.domain.intelligence import CommutePrediction
from metropulse.domain.journey import RideLeg
from metropulse.infrastructure.db.commuter_models import Journey
from metropulse.infrastructure.db.commuter_repositories import JourneyRepository
from metropulse.infrastructure.db.repositories import StopRepository

logger = logging.getLogger(__name__)

_HISTORY_LIMIT = 200
_MIN_SAMPLES_FOR_CONFIDENCE = 8
_SECONDS_PER_DAY = 24 * 3600


class NoCommuteHistoryError(UnknownEntityError):
    """Raised when a user has no journey history to learn a pattern from."""


@dataclass
class _Candidate:
    origin_stop_id: str
    destination_stop_id: str
    route_id: str | None
    seconds_since_midnight: list[float] = field(default_factory=list)


class CommutePredictionService:
    """Predicts a user's next commute from their own completed-journey history."""

    def __init__(
        self,
        planner: JourneyPlanner,
        coach: CoachRecommendationService,
        exits: ExitService,
        *,
        lookback_days: float = 90.0,
        history_limit: int = _HISTORY_LIMIT,
    ) -> None:
        self._planner = planner
        self._coach = coach
        self._exits = exits
        self._lookback = timedelta(days=lookback_days)
        self._history_limit = history_limit

    async def predict(
        self, session: AsyncSession, user_id: str, now: datetime
    ) -> CommutePrediction:
        """The commute this user is most likely making next, right now.

        Raises :class:`NoCommuteHistoryError` when there isn't enough
        journey history (same day-type, within the lookback window) to
        learn a pattern from.
        """
        history = await JourneyRepository(session).history_for_user(
            user_id, self._history_limit
        )
        cutoff = now - self._lookback
        is_weekend = now.weekday() >= 5
        matching = [
            journey
            for journey in history
            if journey.status in ("completed", "missed")
            and _ensure_aware(journey.started_at) >= cutoff
            and (journey.started_at.weekday() >= 5) == is_weekend
        ]
        if not matching:
            raise NoCommuteHistoryError(
                "not enough journey history yet to predict a commute"
            )

        candidate = _closest_to_now(_group_by_endpoints(matching), now)

        stops = StopRepository(session)
        origin = await stops.get(candidate.origin_stop_id)
        destination = await stops.get(candidate.destination_stop_id)
        if origin is None or destination is None:
            raise NoCommuteHistoryError(
                "the predicted stations no longer exist in the current dataset"
            )

        predicted_departure_at = _at_time_of_day(
            now, median(candidate.seconds_since_midnight)
        )

        plan = None
        try:
            plan = await self._planner.plan(
                candidate.origin_stop_id,
                candidate.destination_stop_id,
                departure_at=predicted_departure_at,
            )
        except Exception:
            logger.warning(
                "commute prediction: no route between %s and %s",
                candidate.origin_stop_id,
                candidate.destination_stop_id,
            )

        first_ride = (
            next((leg for leg in plan.legs if isinstance(leg, RideLeg)), None)
            if plan is not None
            else None
        )

        recommended_coach = None
        try:
            recommendation = await self._coach.recommend(
                session,
                candidate.origin_stop_id,
                candidate.destination_stop_id,
                first_ride.route_id if first_ride else candidate.route_id,
                first_ride.direction_id if first_ride else None,
                at=predicted_departure_at,
            )
            recommended_coach = recommendation.recommended_coach
        except UnknownEntityError:
            pass

        recommended_exit_name = None
        try:
            exit_recommendation = await self._exits.recommend(
                session, candidate.destination_stop_id
            )
            if exit_recommendation.best is not None:
                recommended_exit_name = exit_recommendation.best.name
        except UnknownEntityError:
            pass

        sample_size = len(candidate.seconds_since_midnight)
        confidence = min(1.0, sample_size / _MIN_SAMPLES_FOR_CONFIDENCE)

        return CommutePrediction(
            origin_stop_id=candidate.origin_stop_id,
            origin_name=origin.stop_name,
            destination_stop_id=candidate.destination_stop_id,
            destination_name=destination.stop_name,
            route_id=first_ride.route_id if first_ride else candidate.route_id,
            route_long_name=first_ride.route_long_name if first_ride else None,
            predicted_departure_at=predicted_departure_at,
            predicted_duration_seconds=(
                plan.expected_travel_seconds if plan is not None else None
            ),
            recommended_coach=recommended_coach,
            recommended_exit_name=recommended_exit_name,
            confidence=round(confidence, 3),
            sample_size=sample_size,
            basis=_basis_text(is_weekend, sample_size),
        )


def _group_by_endpoints(journeys: Sequence[Journey]) -> dict[tuple[str, str], _Candidate]:
    grouped: dict[tuple[str, str], _Candidate] = {}
    for journey in journeys:
        key = (journey.origin_stop_id, journey.destination_stop_id)
        seconds = (
            journey.started_at.hour * 3600
            + journey.started_at.minute * 60
            + journey.started_at.second
        )
        candidate = grouped.setdefault(
            key,
            _Candidate(
                origin_stop_id=journey.origin_stop_id,
                destination_stop_id=journey.destination_stop_id,
                route_id=journey.route_id,
            ),
        )
        candidate.seconds_since_midnight.append(float(seconds))
    return grouped


def _closest_to_now(grouped: dict[tuple[str, str], _Candidate], now: datetime) -> _Candidate:
    """The most-travelled (origin, destination) pair, tie-broken by how close
    its typical departure time is to right now — so the prediction is for
    the trip the user is actually about to make, not just their all-time
    favourite route."""
    now_seconds = now.hour * 3600 + now.minute * 60 + now.second

    def sort_key(candidate: _Candidate) -> tuple[int, float]:
        count = len(candidate.seconds_since_midnight)
        typical = median(candidate.seconds_since_midnight)
        return (-count, _circular_distance(typical, now_seconds))

    return min(grouped.values(), key=sort_key)


def _circular_distance(a: float, b: float) -> float:
    diff = abs(a - b)
    return min(diff, _SECONDS_PER_DAY - diff)


def _ensure_aware(value: datetime) -> datetime:
    """Treat a naive datetime as UTC.

    ``DateTime(timezone=True)`` round-trips as aware on PostgreSQL but as
    naive on SQLite (used in tests) — this normalises either into a value
    safely comparable against ``utcnow()``.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _at_time_of_day(now: datetime, seconds_since_midnight: float) -> datetime:
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    candidate = midnight + timedelta(seconds=seconds_since_midnight)
    if candidate < now - timedelta(hours=1):
        candidate += timedelta(days=1)
    return candidate


def _basis_text(is_weekend: bool, sample_size: int) -> str:
    day_type = "weekend" if is_weekend else "weekday"
    if sample_size == 1:
        return f"based on your only recent {day_type} trip"
    return f"based on {sample_size} of your recent {day_type} trips"
