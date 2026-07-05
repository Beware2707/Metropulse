"""Domain values for Metro Intelligence.

Every prediction here is derived from GTFS schedules plus the user's own
journey history — never a black-box model. Each carries an explicit
``confidence`` (0..1, scaling with sample size) and, where relevant, the
``sample_size`` it's based on, so callers can be honest about how sure a
prediction really is rather than presenting a guess as a fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CommutePrediction:
    """The commute this user is most likely making right now, learned from
    their own journey history — not a generic "next scheduled train" lookup.
    """

    origin_stop_id: str
    origin_name: str
    destination_stop_id: str
    destination_name: str
    route_id: str | None
    route_long_name: str | None
    predicted_departure_at: datetime
    predicted_duration_seconds: float | None
    recommended_coach: int | None
    recommended_exit_name: str | None
    confidence: float
    sample_size: int
    basis: str


@dataclass(frozen=True, slots=True)
class DelayEstimate:
    """Typical delay for a route around an hour of day, from completed
    journeys' actual duration vs. the GTFS-scheduled duration for the same
    trip. Positive means slower than scheduled, negative means faster.
    """

    route_id: str
    direction_id: int | None
    hour_of_day: int
    expected_delay_seconds: float
    confidence: float
    sample_size: int


@dataclass(frozen=True, slots=True)
class RouteRecommendation:
    """One scored route option inside a smart-recommendation bundle."""

    preference: str
    travel_seconds: float
    interchange_count: int
    walking_distance_m: float
    delay_adjusted_seconds: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SmartRecommendation:
    """The synthesised "what should I do" bundle for an origin/destination.

    ``least_crowded_available`` is always False today: per-coach occupancy
    feeds the coach recommendation already, but route-level crowd-density
    scoring (choosing between whole routes by expected crowding) isn't
    modelled yet — this field is the explicit, honest hook for that future
    capability rather than a fabricated score.
    """

    origin_stop_id: str
    destination_stop_id: str
    best_departure_at: datetime | None
    best_route: RouteRecommendation | None
    alternatives: tuple[RouteRecommendation, ...]
    recommended_coach: int | None
    recommended_exit_name: str | None
    least_crowded_available: bool
