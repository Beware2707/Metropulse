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

from metropulse.application.commuter.contributions import ContributionService
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
        observed: set[int] = set()
        for index in range(coach_count):
            samples = per_coach.get(index, [])
            if len(samples) >= _MIN_SAMPLES_PER_COACH:
                occupancies.append(min(max(sum(samples) / len(samples), 0.0), 1.0))
                samples_used += len(samples)
                observed.add(index)
            else:
                occupancies.append(prior[index])
        return CrowdForecast(
            occupancies=tuple(occupancies),
            source="observed" if observed else "prior",
            model_version=None,
            sample_count=samples_used,
            observed_coaches=frozenset(observed),
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

        exit_repo = StationExitRepository(session)
        hints = await exit_repo.hints_for(
            destination_stop_id, route_id=route_id, direction_id=direction_id
        )
        # Gate names for those hints, so a reason can name the gate a rider
        # will actually see signposted rather than gesture at "an exit".
        exit_names = await exit_repo.hint_exit_names_for(
            destination_stop_id, route_id=route_id, direction_id=direction_id
        )
        # Claims enough separate riders have confirmed. Curated hints win where
        # both exist — DMRC's own mapping outranks eyewitness agreement — but
        # rider knowledge fills the (currently total) gaps, and stays labelled
        # as rider knowledge all the way to the screen.
        rider_exits = await ContributionService().confirmed_coach_exits(
            session, destination_stop_id, route_id=route_id, direction_id=direction_id
        )
        rider_only = {k: v for k, v in rider_exits.items() if k not in exit_names}
        hint_coaches = sorted(
            {h.coach_index for h in hints if h.coach_index >= 0} | set(rider_only)
        )
        coach_count = self._default_coach_count
        if hint_coaches:
            coach_count = max(coach_count, hint_coaches[-1] + 1)

        forecast = await self._predictor.coach_occupancy(
            route_id, direction_id, at, coach_count
        )

        # Coach 1 (index 0) is reserved for women only on Delhi Metro -- the
        # app has no way to know a rider's eligibility to board it, so it
        # must never appear as a general recommendation regardless of how
        # empty or exit-aligned it scores. Excluded only when there's a real
        # alternative; a degenerate single-coach configuration still returns
        # its one coach rather than recommending nothing.
        excluded = {0} if coach_count > 1 else set()
        scores = [
            self._score_coach(
                index, forecast, hint_coaches, coach_count, exit_names, rider_only
            )
            for index in range(coach_count)
            if index not in excluded
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
        exit_names: dict[int, str] | None = None,
        rider_exit_names: dict[int, str] | None = None,
    ) -> CoachScore:
        occupancy = forecast.occupancies[index]
        if hint_coaches:
            distance = min(abs(index - hint) for hint in hint_coaches)
            alignment = 1.0 - distance / max(coach_count - 1, 1)
        else:
            alignment = 0.5  # no exit data: neutral, crowding decides

        score = self._crowd_weight * (1.0 - occupancy) + self._exit_weight * alignment
        reasons = [
            # Per-coach provenance, not the forecast-wide label: in a mixed
            # forecast this coach's number may be a prior even when others
            # were observed.
            *_crowd_reasons(occupancy, observed=index in forecast.observed_coaches),
            *_exit_reasons(
                index,
                hint_coaches,
                alignment,
                coach_count,
                exit_names or {},
                rider_exit_names or {},
            ),
        ]
        return CoachScore(
            coach_index=index,
            occupancy=round(occupancy, 3),
            exit_alignment=round(alignment, 3),
            score=round(score, 4),
            reasons=tuple(reasons),
        )


def _crowd_reasons(occupancy: float, *, observed: bool) -> list[str]:
    """The crowd half of a coach's explanation, pitched at its evidence.

    "Typically less crowded" is a claim about how this line actually runs, and
    a rider is entitled to read it that way. It is only earned when THIS
    coach's number came from real observations. Otherwise the number is the
    triangular prior — a generic assumption that trains fill toward the
    middle, identical on every line, in every direction, at every hour — so
    the wording has to say so. Dressing a constant as a measurement is exactly
    the failure this codebase exists not to make.
    """
    if observed:
        if occupancy <= 0.45:
            return ["typically less crowded"]
        if occupancy >= 0.7:
            return ["typically crowded"]
        return []
    if occupancy <= 0.45:
        return ["end coaches are usually lighter — no crowd data for this line yet"]
    return []


def _exit_reasons(
    index: int,
    hint_coaches: list[int],
    alignment: float,
    coach_count: int,
    exit_names: dict[int, str],
    rider_exit_names: dict[int, str],
) -> list[str]:
    """The exit half: name the gate whenever anything gives us one.

    "Closest to Gate No. 4" is checkable against the signs overhead; "stops
    nearest to a destination exit" is not. Unnamed phrasing is kept only for
    the case where a hint exists but its exit row has no usable name.

    Rider-confirmed claims are worded differently on purpose. "Riders say Gate
    No. 4 is closest" tells someone where the knowledge came from, so they can
    weigh it themselves — three commuters agreeing is good evidence, and it is
    still not DMRC's own mapping. Blending the two into one confident sentence
    would be the small dishonesty that makes every other claim suspect.
    """
    if not hint_coaches:
        return []

    def phrase(coach: int, curated: str, rider: str) -> list[str]:
        if (name := exit_names.get(coach)) is not None:
            return [curated.format(name=name)]
        if (name := rider_exit_names.get(coach)) is not None:
            return [rider.format(name=name)]
        return [curated.format(name="a destination exit").replace("Gate", "gate")]

    if index in hint_coaches:
        return phrase(index, "closest to {name}", "riders say {name} is closest")
    if alignment >= 0.75:
        nearest = min(hint_coaches, key=lambda hint: (abs(index - hint), hint))
        return phrase(
            nearest, "short walk to {name}", "riders say {name} is a short walk"
        )
    return []


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
