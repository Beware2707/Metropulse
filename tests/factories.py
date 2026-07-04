"""Test object factories: domain vehicles and GTFS-RT protobuf payloads."""

from __future__ import annotations

from datetime import UTC, datetime

from google.transit import gtfs_realtime_pb2

from metropulse.domain.entities import VehiclePosition


def make_vehicle(
    vehicle_id: str = "v1",
    latitude: float = 28.60,
    longitude: float = 77.015,
    trip_id: str | None = "T1",
    route_id: str | None = "R1",
    speed_mps: float | None = 10.0,
    timestamp: datetime | None = None,
) -> VehiclePosition:
    """A domain vehicle position with sensible defaults on the fixture line."""
    return VehiclePosition(
        vehicle_id=vehicle_id,
        latitude=latitude,
        longitude=longitude,
        timestamp=timestamp or datetime.now(UTC),
        trip_id=trip_id,
        route_id=route_id,
        speed_mps=speed_mps,
    )


def build_feed_payload(
    vehicles: list[VehiclePosition], header_timestamp: int | None = None
) -> bytes:
    """Serialize domain vehicles into a GTFS-RT FeedMessage payload."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    if header_timestamp is not None:
        feed.header.timestamp = header_timestamp
    for index, vehicle in enumerate(vehicles):
        entity = feed.entity.add()
        entity.id = f"e{index}"
        vp = entity.vehicle
        vp.vehicle.id = vehicle.vehicle_id
        vp.position.latitude = vehicle.latitude
        vp.position.longitude = vehicle.longitude
        if vehicle.speed_mps is not None:
            vp.position.speed = vehicle.speed_mps
        if vehicle.bearing is not None:
            vp.position.bearing = vehicle.bearing
        if vehicle.trip_id:
            vp.trip.trip_id = vehicle.trip_id
        if vehicle.route_id:
            vp.trip.route_id = vehicle.route_id
        vp.timestamp = int(vehicle.timestamp.timestamp())
    return feed.SerializeToString()
