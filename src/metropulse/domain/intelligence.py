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
from enum import Enum


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


class PlaceRole(str, Enum):
    """A role inferred for a place from movement patterns, not user input.

    Movement data alone can't tell "Office" from "College" — both are simply
    the place a user travels to and from on a regular weekday schedule. So
    this models exactly two roles: ``HOME`` (where trips most often start)
    and ``WEEKDAY_ANCHOR`` (where they most often go on weekdays from home).
    The UI is expected to let the user confirm or relabel the real name.
    """

    HOME = "home"
    WEEKDAY_ANCHOR = "weekday_anchor"


@dataclass(frozen=True, slots=True)
class InferredPlace:
    """A place role inferred from a user's own journey history.

    This is a suggestion, not a fact written on the user's behalf: callers
    should offer it for confirmation (e.g. pre-filling a Favourites label)
    rather than silently overwriting anything the user already set.
    """

    stop_id: str
    stop_name: str
    role: PlaceRole
    confidence: float
    sample_size: int
    rationale: str
