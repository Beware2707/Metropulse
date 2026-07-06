"""Domain values for commuter features (pure, framework-free)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class LastTrainInfo:
    """The last boardable departure from a stop for a service day."""

    stop_id: str
    route_id: str
    trip_id: str
    direction_id: int | None
    headsign: str | None
    service_date: date
    departure_seconds: int
    departure_at: datetime


@dataclass(frozen=True, slots=True)
class CrowdForecast:
    """Per-coach occupancy forecast in [0, 1] with provenance."""

    occupancies: tuple[float, ...]
    source: str  # observed|prior|model
    model_version: str | None
    sample_count: int


@dataclass(frozen=True, slots=True)
class CoachScore:
    """One coach's ranking inside a recommendation."""

    coach_index: int
    occupancy: float
    exit_alignment: float
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CoachRecommendation:
    """Ranked coach choices for a journey.

    ``coach_count`` is the train's true physical coach count (needed intact
    for exit-alignment math against real coach-index hints); ``coaches`` is
    one entry shorter whenever ``coach_count > 1``, since coach index 0 (the
    women-reserved coach on Delhi Metro) is never a candidate for a general
    recommendation and so never appears in it.
    """

    origin_stop_id: str
    destination_stop_id: str
    coach_count: int
    crowd_source: str
    model_version: str | None
    recommended_coach: int
    coaches: tuple[CoachScore, ...]


@dataclass(frozen=True, slots=True)
class ExitOption:
    """One station exit as a ranked recommendation entry."""

    exit_id: int
    name: str
    description: str | None
    landmarks: tuple[str, ...]
    matched_landmark: str | None
    nearest_coach_index: int | None
    score: float


@dataclass(frozen=True, slots=True)
class ExitRecommendation:
    """Ranked exits for a destination station."""

    stop_id: str
    query_landmark: str | None
    exits: tuple[ExitOption, ...]

    @property
    def best(self) -> ExitOption | None:
        """The top-ranked exit, if any exist."""
        return self.exits[0] if self.exits else None


@dataclass(frozen=True, slots=True)
class OfflineManifest:
    """Metadata clients use to decide whether to re-sync the offline bundle."""

    version: str
    checksum: str
    generated_at: datetime
    station_count: int
    route_count: int
