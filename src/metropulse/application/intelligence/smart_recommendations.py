"""Smart recommendations: synthesises the journey planner, delay estimates,
and the existing coach/exit engines into a single "what should I do" bundle
for an origin/destination pair.

Every :data:`~metropulse.application.journey_planner.ROUTE_PREFERENCES` is
planned and delay-adjusted; the cheapest delay-adjusted option wins. "Best
departure time" is today's requested time pulled earlier by the route's
typical delay, when that delay is meaningful — a concrete, explainable
answer rather than a black-box suggestion.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.commuter.coach import CoachRecommendationService
from metropulse.application.commuter.exits import ExitService
from metropulse.application.journey_planner import ROUTE_PREFERENCES, JourneyPlanner
from metropulse.application.ports import DelayEstimator
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.domain.intelligence import RouteRecommendation, SmartRecommendation
from metropulse.domain.journey import JourneyPlan, RideLeg

_MEANINGFUL_DELAY_SECONDS = 60.0

_PREFERENCE_LABELS = {
    "fastest": "shortest scheduled travel time",
    "fewer_transfers": "fewest interchanges",
    "less_walking": "least walking",
}


class SmartRecommendationService:
    """Best route / departure / coach / exit for an origin-destination pair."""

    def __init__(
        self,
        planner: JourneyPlanner,
        coach: CoachRecommendationService,
        exits: ExitService,
        delay: DelayEstimator,
    ) -> None:
        self._planner = planner
        self._coach = coach
        self._exits = exits
        self._delay = delay

    async def recommend(
        self,
        session: AsyncSession,
        origin_stop_id: str,
        destination_stop_id: str,
        at: datetime,
    ) -> SmartRecommendation:
        """Compare every route preference and recommend the best one.

        Raises :class:`~metropulse.domain.exceptions.UnknownEntityError` for
        unknown stops and :class:`~metropulse.domain.exceptions.NoRouteError`
        (both surfaced by the planner) when nothing connects the two stations.
        """
        plans: dict[str, JourneyPlan] = {}
        options: dict[str, RouteRecommendation] = {}
        for preference in ROUTE_PREFERENCES:
            plan = await self._planner.plan(
                origin_stop_id, destination_stop_id, departure_at=at, preference=preference
            )
            plans[preference] = plan
            options[preference] = await self._score(session, plan, preference, at)

        best_preference = min(options, key=lambda pref: options[pref].delay_adjusted_seconds)
        best = options[best_preference]
        best_plan = plans[best_preference]
        alternatives = tuple(rec for pref, rec in options.items() if pref != best_preference)

        delay_buffer = max(best.delay_adjusted_seconds - best.travel_seconds, 0.0)
        best_departure_at = (
            at - timedelta(seconds=delay_buffer)
            if delay_buffer >= _MEANINGFUL_DELAY_SECONDS
            else at
        )

        first_ride = next((leg for leg in best_plan.legs if isinstance(leg, RideLeg)), None)

        recommended_coach = None
        try:
            coach_recommendation = await self._coach.recommend(
                session,
                origin_stop_id,
                destination_stop_id,
                first_ride.route_id if first_ride else None,
                first_ride.direction_id if first_ride else None,
                at=at,
            )
            recommended_coach = coach_recommendation.recommended_coach
        except UnknownEntityError:
            pass

        recommended_exit_name = None
        try:
            exit_recommendation = await self._exits.recommend(session, destination_stop_id)
            if exit_recommendation.best is not None:
                recommended_exit_name = exit_recommendation.best.name
        except UnknownEntityError:
            pass

        return SmartRecommendation(
            origin_stop_id=origin_stop_id,
            destination_stop_id=destination_stop_id,
            best_departure_at=best_departure_at,
            best_route=best,
            alternatives=alternatives,
            recommended_coach=recommended_coach,
            recommended_exit_name=recommended_exit_name,
            least_crowded_available=False,
        )

    async def _score(
        self,
        session: AsyncSession,
        plan: JourneyPlan,
        preference: str,
        at: datetime,
    ) -> RouteRecommendation:
        first_ride = next((leg for leg in plan.legs if isinstance(leg, RideLeg)), None)
        delay_seconds = 0.0
        if first_ride is not None:
            delay = await self._delay.estimate(session, first_ride.route_id, first_ride.direction_id, at)
            delay_seconds = max(delay.expected_delay_seconds, 0.0)

        reasons = [_PREFERENCE_LABELS[preference]]
        if delay_seconds >= _MEANINGFUL_DELAY_SECONDS:
            reasons.append(f"usually runs about {round(delay_seconds / 60)} min behind schedule")

        return RouteRecommendation(
            preference=preference,
            travel_seconds=plan.expected_travel_seconds,
            interchange_count=plan.interchange_count,
            walking_distance_m=plan.walking_distance_m,
            delay_adjusted_seconds=plan.expected_travel_seconds + delay_seconds,
            reasons=tuple(reasons),
        )
