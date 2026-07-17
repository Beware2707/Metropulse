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
    """A single decoded vehicle position from the realtime feed.

    ``source`` is the honest label for where this position actually came
    from: ``"realtime_gps"`` (an actual GTFS-Realtime feed, set explicitly
    by ``infrastructure/gtfs_rt/decoder.py``) or ``"schedule_estimate"``
    (interpolated from the static timetable when no licensed realtime feed
    is configured, set explicitly by ``application/schedule_position_source.py``).
    The default is ``"unknown"`` so a position that reaches a consumer
    without an explicitly declared origin is never silently mislabeled as
    live GPS. Every consumer -- WS payloads, the REST API, the Flutter map
    -- reads this field rather than assuming positions are always live
    telemetry.
    """

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
    source: str = "unknown"

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
            "source": self.source,
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
            source=data.get("source", "unknown"),
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StationRef":
        """Deserialize from :meth:`to_dict` output."""
        return cls(stop_id=data["stop_id"], name=data["name"], sequence=data["sequence"])


@dataclass(frozen=True, slots=True)
class TrainLocation:
    """Where along its trip a vehicle currently is."""

    current_station: StationRef | None
    next_station: StationRef | None
    destination: StationRef | None
    at_station: bool
    distance_along_m: float | None
    shape_offset_m: float | None
    remaining_stations: tuple[StationRef, ...] = ()


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
    remaining_stations: tuple[StationRef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict for REST, WS and Redis caching."""
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
            "remaining_stations": [s.to_dict() for s in self.remaining_stations],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrainState":
        """Deserialize from :meth:`to_dict` output (Redis-cached states)."""

        def _ref(value: dict[str, Any] | None) -> StationRef | None:
            return StationRef.from_dict(value) if value else None

        return cls(
            vehicle=VehiclePosition.from_dict(data["vehicle"]),
            resolved=data["resolved"],
            is_stale=data["is_stale"],
            route_id=data.get("route_id"),
            route_short_name=data.get("route_short_name"),
            route_long_name=data.get("route_long_name"),
            route_color=data.get("route_color"),
            headsign=data.get("headsign"),
            direction_id=data.get("direction_id"),
            current_station=_ref(data.get("current_station")),
            next_station=_ref(data.get("next_station")),
            destination=_ref(data.get("destination")),
            at_station=data.get("at_station", False),
            distance_along_m=data.get("distance_along_m"),
            shape_offset_m=data.get("shape_offset_m"),
            remaining_stations=tuple(
                StationRef.from_dict(s) for s in data.get("remaining_stations", [])
            ),
        )


@dataclass(frozen=True, slots=True)
class StationEta:
    """ETA to one remaining station on a vehicle's trip."""

    stop_id: str
    stop_name: str
    sequence: int
    distance_remaining_m: float
    eta_seconds: float
    eta_time: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "stop_id": self.stop_id,
            "stop_name": self.stop_name,
            "sequence": self.sequence,
            "distance_remaining_m": self.distance_remaining_m,
            "eta_seconds": self.eta_seconds,
            "eta_time": self.eta_time.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StationEta":
        """Deserialize from :meth:`to_dict` output."""
        return cls(
            stop_id=data["stop_id"],
            stop_name=data["stop_name"],
            sequence=data["sequence"],
            distance_remaining_m=data["distance_remaining_m"],
            eta_seconds=data["eta_seconds"],
            eta_time=datetime.fromisoformat(data["eta_time"]),
        )


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
    next_station: StationEta | None = None
    delay_seconds: float | None = None
    dwell_seconds_used: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict (Redis ETA cache)."""
        return {
            "vehicle_id": self.vehicle_id,
            "trip_id": self.trip_id,
            "computed_at": self.computed_at.isoformat(),
            "speed_mps_used": self.speed_mps_used,
            "speed_source": self.speed_source,
            "confidence": self.confidence,
            "stations": [s.to_dict() for s in self.stations],
            "next_station": self.next_station.to_dict() if self.next_station else None,
            "delay_seconds": self.delay_seconds,
            "dwell_seconds_used": self.dwell_seconds_used,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VehicleEta":
        """Deserialize from :meth:`to_dict` output."""
        next_station = data.get("next_station")
        return cls(
            vehicle_id=data["vehicle_id"],
            trip_id=data["trip_id"],
            computed_at=datetime.fromisoformat(data["computed_at"]),
            speed_mps_used=data["speed_mps_used"],
            speed_source=data["speed_source"],
            confidence=data["confidence"],
            stations=tuple(StationEta.from_dict(s) for s in data["stations"]),
            next_station=StationEta.from_dict(next_station) if next_station else None,
            delay_seconds=data.get("delay_seconds"),
            dwell_seconds_used=data.get("dwell_seconds_used", 0.0),
        )


def utcnow() -> datetime:
    """Timezone-aware current UTC time (single seam for tests)."""
    return datetime.now(UTC)
