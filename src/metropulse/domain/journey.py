"""Domain values for journey planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class JourneyStop:
    """A station reference within a journey plan."""

    stop_id: str
    name: str


@dataclass(frozen=True, slots=True)
class RideLeg:
    """One continuous ride on a single line/direction.

    Carries exactly the identifiers (route_id, direction_id, boarding and
    alighting stops) a coach-recommendation or crowd-prediction engine needs
    to annotate the leg later — extension happens by composition, not by
    changing this type.
    """

    board: JourneyStop
    alight: JourneyStop
    route_id: str
    route_short_name: str | None
    route_long_name: str | None
    route_color: str | None
    direction_id: int | None
    platform_hint: str
    stations: tuple[JourneyStop, ...]
    ride_seconds: float
    wait_seconds: float

    @property
    def kind(self) -> str:
        """Leg discriminator."""
        return "ride"


@dataclass(frozen=True, slots=True)
class WalkLeg:
    """A walking transfer between two nearby stations."""

    board: JourneyStop
    alight: JourneyStop
    distance_m: float
    walk_seconds: float

    @property
    def kind(self) -> str:
        """Leg discriminator."""
        return "walk"


JourneyLeg = RideLeg | WalkLeg


@dataclass(frozen=True, slots=True)
class JourneyPlan:
    """A complete origin-to-destination plan."""

    origin: JourneyStop
    destination: JourneyStop
    departure_at: datetime
    expected_arrival_at: datetime
    expected_travel_seconds: float
    interchange_count: int
    walking_distance_m: float
    legs: tuple[JourneyLeg, ...]

    @property
    def remaining_stations(self) -> tuple[JourneyStop, ...]:
        """Every station passed after boarding, across all ride legs."""
        stations: list[JourneyStop] = []
        for leg in self.legs:
            if isinstance(leg, RideLeg):
                stations.extend(leg.stations[1:])
        return tuple(stations)

    @property
    def interchange_stops(self) -> tuple[JourneyStop, ...]:
        """The stations where the rider changes lines (alighting points)."""
        rides = [leg for leg in self.legs if isinstance(leg, RideLeg)]
        return tuple(leg.alight for leg in rides[:-1])
