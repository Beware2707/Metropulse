"""Application-layer ports (Protocols) for swappable strategies.

These are the seams where AI models plug in later WITHOUT schema or API
changes: implement the Protocol, write predictions into the existing tables
(``crowd_observations`` with source='model'), and swap the binding in wiring.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.domain.commuter import CrowdForecast
from metropulse.domain.entities import StopOnTrip, TripContext, VehiclePosition
from metropulse.domain.intelligence import CommutePrediction, DelayEstimate, SmartRecommendation


class CrowdPredictor(Protocol):
    """Predicts per-coach occupancy for a route/direction at a time."""

    async def coach_occupancy(
        self,
        route_id: str | None,
        direction_id: int | None,
        at: datetime,
        coach_count: int,
    ) -> CrowdForecast:
        """Return occupancy per coach in [0, 1] with provenance."""
        ...


class TravelTimePredictor(Protocol):
    """Predicts travel time (seconds, dwell included) to each remaining stop.

    Returning None means "no prediction available"; the ETA engine then falls
    back to its physics-based heuristic. This is the seam for an ML ETA model.
    """

    async def predict_travel_seconds(
        self,
        vehicle: VehiclePosition,
        context: TripContext,
        remaining_stops: Sequence[StopOnTrip],
    ) -> list[float] | None:
        """Seconds until arrival, aligned index-for-index with remaining_stops."""
        ...


class NotificationChannel(Protocol):
    """A delivery transport for user notifications (push, log, webhook...)."""

    async def deliver(
        self, user_id: str, kind: str, title: str, body: str, payload: dict[str, Any] | None
    ) -> bool:
        """Attempt delivery; return True on success."""
        ...


class CommutePredictor(Protocol):
    """Predicts a user's next commute.

    Today's binding (:class:`~metropulse.application.intelligence.commute_predictor.CommutePredictionService`)
    mines the user's own journey history. This seam is what lets a future
    per-user ML model or an LLM-backed reasoner replace that rule-based
    strategy without touching the API router, the proactive scheduler, or the
    voice assistant that all depend on this Protocol rather than the concrete
    class.
    """

    async def predict(
        self, session: AsyncSession, user_id: str, now: datetime
    ) -> CommutePrediction:
        """The commute this user is most likely making next, right now."""
        ...


class DelayEstimator(Protocol):
    """Estimates typical delay for a route around a time of day.

    Today's binding compares historical completed-journey durations against
    the GTFS-scheduled duration. Swapping in GTFS-Realtime (or a learned
    delay model) once it's available is a wiring change only.
    """

    async def estimate(
        self,
        session: AsyncSession,
        route_id: str,
        direction_id: int | None,
        at: datetime,
    ) -> DelayEstimate:
        """Typical delay for the route around the given time of day."""
        ...


class RecommendationEngine(Protocol):
    """Synthesises the best route/departure/coach/exit for a trip.

    Today's binding composes the journey planner, coach recommender, exit
    recommender and delay estimator with rule-based scoring. The seam allows
    that scoring to be replaced (e.g. with a learned ranker) without touching
    the API router.
    """

    async def recommend(
        self,
        session: AsyncSession,
        origin_stop_id: str,
        destination_stop_id: str,
        at: datetime,
    ) -> SmartRecommendation:
        """The best route, departure time, coach and exit for this trip."""
        ...
