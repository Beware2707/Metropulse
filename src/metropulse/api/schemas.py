"""Pydantic response schemas for the public REST API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from metropulse.domain.entities import (
    StationEta,
    StationRef,
    TrainState,
    VehicleEta,
    VehiclePosition,
)
from metropulse.infrastructure.db.models import Route, Stop


class VehicleOut(BaseModel):
    """Raw vehicle position fields."""

    vehicle_id: str
    latitude: float
    longitude: float
    timestamp: datetime
    trip_id: str | None
    route_id: str | None
    bearing: float | None
    speed_mps: float | None
    label: str | None
    current_status: str | None
    current_stop_id: str | None
    source: str

    @classmethod
    def from_domain(cls, vehicle: VehiclePosition) -> "VehicleOut":
        """Build from the domain entity."""
        return cls(
            vehicle_id=vehicle.vehicle_id,
            latitude=vehicle.latitude,
            longitude=vehicle.longitude,
            timestamp=vehicle.timestamp,
            trip_id=vehicle.trip_id,
            route_id=vehicle.route_id,
            bearing=vehicle.bearing,
            speed_mps=vehicle.speed_mps,
            label=vehicle.label,
            current_status=vehicle.current_status.value if vehicle.current_status else None,
            current_stop_id=vehicle.current_stop_id,
            source=vehicle.source,
        )


class StationRefOut(BaseModel):
    """Station reference within a train payload."""

    stop_id: str
    name: str
    sequence: int

    @classmethod
    def from_domain(cls, ref: StationRef | None) -> "StationRefOut | None":
        """Build from the domain value, passing None through."""
        if ref is None:
            return None
        return cls(stop_id=ref.stop_id, name=ref.name, sequence=ref.sequence)


class TrainOut(BaseModel):
    """Enriched train state."""

    vehicle: VehicleOut
    resolved: bool
    is_stale: bool
    route_id: str | None
    route_short_name: str | None
    route_long_name: str | None
    route_color: str | None
    headsign: str | None
    direction_id: int | None
    current_station: StationRefOut | None
    next_station: StationRefOut | None
    destination: StationRefOut | None
    at_station: bool
    distance_along_m: float | None
    shape_offset_m: float | None
    remaining_stations: list[StationRefOut]

    @classmethod
    def from_domain(cls, state: TrainState) -> "TrainOut":
        """Build from the domain entity."""
        remaining = [
            ref
            for ref in (StationRefOut.from_domain(s) for s in state.remaining_stations)
            if ref is not None
        ]
        return cls(
            vehicle=VehicleOut.from_domain(state.vehicle),
            resolved=state.resolved,
            is_stale=state.is_stale,
            route_id=state.route_id,
            route_short_name=state.route_short_name,
            route_long_name=state.route_long_name,
            route_color=state.route_color,
            headsign=state.headsign,
            direction_id=state.direction_id,
            current_station=StationRefOut.from_domain(state.current_station),
            next_station=StationRefOut.from_domain(state.next_station),
            destination=StationRefOut.from_domain(state.destination),
            at_station=state.at_station,
            distance_along_m=state.distance_along_m,
            shape_offset_m=state.shape_offset_m,
            remaining_stations=remaining,
        )


class TrainListOut(BaseModel):
    """Envelope for the trains collection."""

    count: int
    trains: list[TrainOut]


class RouteOut(BaseModel):
    """A GTFS route."""

    model_config = ConfigDict(from_attributes=True)

    route_id: str
    agency_id: str | None
    route_short_name: str | None
    route_long_name: str | None
    route_type: int
    route_color: str | None
    route_text_color: str | None

    @classmethod
    def from_orm_route(cls, route: Route) -> "RouteOut":
        """Build from the ORM row."""
        return cls.model_validate(route)


class RouteListOut(BaseModel):
    """Envelope for the routes collection."""

    count: int
    routes: list[RouteOut]


class StationOut(BaseModel):
    """A GTFS stop/station."""

    model_config = ConfigDict(from_attributes=True)

    stop_id: str
    stop_code: str | None
    stop_name: str
    stop_lat: float
    stop_lon: float
    zone_id: str | None
    location_type: int | None
    parent_station: str | None

    @classmethod
    def from_orm_stop(cls, stop: Stop) -> "StationOut":
        """Build from the ORM row."""
        return cls.model_validate(stop)


class StationDetailOut(StationOut):
    """Station detail including the routes serving it."""

    routes: list[RouteOut]


class StationListOut(BaseModel):
    """Envelope for the stations collection."""

    count: int
    stations: list[StationOut]


class StationEtaOut(BaseModel):
    """ETA to one station."""

    stop_id: str
    stop_name: str
    sequence: int
    distance_remaining_m: float
    eta_seconds: float
    eta_time: datetime

    @classmethod
    def from_domain(cls, eta: StationEta) -> "StationEtaOut":
        """Build from the domain value."""
        return cls(
            stop_id=eta.stop_id,
            stop_name=eta.stop_name,
            sequence=eta.sequence,
            distance_remaining_m=eta.distance_remaining_m,
            eta_seconds=eta.eta_seconds,
            eta_time=eta.eta_time,
        )


class VehicleEtaOut(BaseModel):
    """Full ETA fan-out for a vehicle."""

    vehicle_id: str
    trip_id: str
    computed_at: datetime
    speed_mps_used: float
    speed_source: str
    confidence: str
    next_station: StationEtaOut | None
    delay_seconds: float | None
    dwell_seconds_used: float
    stations: list[StationEtaOut]

    @classmethod
    def from_domain(cls, eta: VehicleEta) -> "VehicleEtaOut":
        """Build from the domain entity."""
        return cls(
            vehicle_id=eta.vehicle_id,
            trip_id=eta.trip_id,
            computed_at=eta.computed_at,
            speed_mps_used=eta.speed_mps_used,
            speed_source=eta.speed_source,
            confidence=eta.confidence,
            next_station=(
                StationEtaOut.from_domain(eta.next_station) if eta.next_station else None
            ),
            delay_seconds=eta.delay_seconds,
            dwell_seconds_used=eta.dwell_seconds_used,
            stations=[StationEtaOut.from_domain(s) for s in eta.stations],
        )


class HealthOut(BaseModel):
    """Health-check response."""

    status: str
    database: bool
    redis: bool
    feed: str  # ok | stale | unknown
    feed_age_seconds: float | None
