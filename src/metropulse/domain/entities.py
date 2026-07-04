"""Domain entities and value objects.

Frozen dataclasses give structural equality for free, which the realtime
engine relies on to detect changed vehicles between polls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from metropulse.domain.geometry import ShapeGeometry


class VehicleStopStatus(StrEnum):
    """GTFS-Realtime VehicleStopStatus values."""

    INCOMING_AT = "INCOMING_AT"
    STOPPED_AT = "STOPPED_AT"
    IN_TRANSIT_TO = "IN_TRANSIT_TO"


@dataclass(frozen=True, slots=True)
class VehiclePosition:
    """A single decoded vehicle position from the realtime feed."""

    vehicle_id: str
    latitude: float
    longitude: float
    timestamp: datetime
    trip_id: str | None = None
    route_id: str | None = None
    bearing: float | None = None
    speed_mps: float | None = None
    label: str | None = None
    current_status: VehicleStopStatus | None = None
    current_stop_id: str | None = None

    def is_stale(self, now: datetime, stale_after_seconds: float) -> bool:
        """Whether this position's own timestamp is older than the threshold."""
        return (now - self.timestamp).total_seconds() > stale_after_seconds

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict (ISO timestamps)."""
        return {
            "vehicle_id": self.vehicle_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timestamp": self.timestamp.isoformat(),
            "trip_id": self.trip_id,
            "route_id": self.route_id,
            "bearing": self.bearing,
            "speed_mps": self.speed_mps,
            "label": self.label,
            "current_status": self.current_status.value if self.current_status else None,
            "current_stop_id": self.current_stop_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VehiclePosition":
        """Deserialize from :meth:`to_dict` output."""
        status = data.get("current_status")
        return cls(
            vehicle_id=data["vehicle_id"],
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            trip_id=data.get("trip_id"),
            route_id=data.get("route_id"),
            bearing=data.get("bearing"),
            speed_mps=data.get("speed_mps"),
            label=data.get("label"),
            current_status=VehicleStopStatus(status) if status else None,
            current_stop_id=data.get("current_stop_id"),
        )


@dataclass(frozen=True, slots=True)
class StopOnTrip:
    """A stop within a trip's ordered station sequence."""

    stop_id: str
    stop_name: str
    sequence: int
    latitude: float
    longitude: float
    arrival_seconds: int
    departure_seconds: int
    distance_along_shape_m: float


@dataclass(frozen=True)
class TripContext:
    """Everything needed to interpret a vehicle position on a known trip."""

    trip_id: str
    route_id: str
    route_short_name: str | None
    route_long_name: str | None
    route_color: str | None
    headsign: str | None
    direction_id: int | None
    shape_id: str | None
    stops: tuple[StopOnTrip, ...]
    geometry: ShapeGeometry | None = field(compare=False)

    @property
    def destination(self) -> StopOnTrip | None:
        """The final stop of the trip, if any stops exist."""
        return self.stops[-1] if self.stops else None


@dataclass(frozen=True, slots=True)
class StationRef:
    """Lightweight reference to a station in API/WS payloads."""

    stop_id: str
    name: str
    sequence: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {"stop_id": self.stop_id, "name": self.name, "sequence": self.sequence}


@dataclass(frozen=True, slots=True)
class TrainLocation:
    """Where along its trip a vehicle currently is."""

    current_station: StationRef | None
    next_station: StationRef | None
    destination: StationRef | None
    at_station: bool
    distance_along_m: float | None
    shape_offset_m: float | None


@dataclass(frozen=True, slots=True)
class TrainState:
    """Enriched, presentation-ready state of one train."""

    vehicle: VehiclePosition
    resolved: bool
    is_stale: bool
    route_id: str | None = None
    route_short_name: str | None = None
    route_long_name: str | None = None
    route_color: str | None = None
    headsign: str | None = None
    direction_id: int | None = None
    current_station: StationRef | None = None
    next_station: StationRef | None = None
    destination: StationRef | None = None
    at_station: bool = False
    distance_along_m: float | None = None
    shape_offset_m: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict for REST and WS payloads."""
        return {
            "vehicle": self.vehicle.to_dict(),
            "resolved": self.resolved,
            "is_stale": self.is_stale,
            "route_id": self.route_id,
            "route_short_name": self.route_short_name,
            "route_long_name": self.route_long_name,
            "route_color": self.route_color,
            "headsign": self.headsign,
            "direction_id": self.direction_id,
            "current_station": self.current_station.to_dict() if self.current_station else None,
            "next_station": self.next_station.to_dict() if self.next_station else None,
            "destination": self.destination.to_dict() if self.destination else None,
            "at_station": self.at_station,
            "distance_along_m": self.distance_along_m,
            "shape_offset_m": self.shape_offset_m,
        }


@dataclass(frozen=True, slots=True)
class StationEta:
    """ETA to one remaining station on a vehicle's trip."""

    stop_id: str
    stop_name: str
    sequence: int
    distance_remaining_m: float
    eta_seconds: float
    eta_time: datetime


@dataclass(frozen=True, slots=True)
class VehicleEta:
    """Full ETA fan-out for one vehicle."""

    vehicle_id: str
    trip_id: str
    computed_at: datetime
    speed_mps_used: float
    speed_source: str
    confidence: str
    stations: tuple[StationEta, ...]


def utcnow() -> datetime:
    """Timezone-aware current UTC time (single seam for tests)."""
    return datetime.now(UTC)
