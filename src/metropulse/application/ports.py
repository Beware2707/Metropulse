"""Application-layer ports (Protocols) for swappable strategies.

These are the seams where AI models plug in later WITHOUT schema or API
changes: implement the Protocol, write predictions into the existing tables
(``crowd_observations`` with source='model'), and swap the binding in wiring.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, Sequence

from metropulse.domain.commuter import CrowdForecast
from metropulse.domain.entities import StopOnTrip, TripContext, VehiclePosition


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
