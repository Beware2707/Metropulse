"""Decoder from GTFS-Realtime protobuf payloads to domain vehicle positions."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from metropulse.domain.entities import VehiclePosition, VehicleStopStatus
from metropulse.domain.exceptions import FeedDecodeError

logger = logging.getLogger(__name__)

_STATUS_BY_NUMBER = {
    gtfs_realtime_pb2.VehiclePosition.INCOMING_AT: VehicleStopStatus.INCOMING_AT,
    gtfs_realtime_pb2.VehiclePosition.STOPPED_AT: VehicleStopStatus.STOPPED_AT,
    gtfs_realtime_pb2.VehiclePosition.IN_TRANSIT_TO: VehicleStopStatus.IN_TRANSIT_TO,
}


def decode_vehicle_positions(
    payload: bytes, fallback_timestamp: datetime | None = None
) -> list[VehiclePosition]:
    """Decode a FeedMessage payload into domain vehicle positions.

    Entities without a vehicle or position block are skipped with a warning.
    ``fallback_timestamp`` is used when neither the entity nor the feed header
    carries a timestamp; it defaults to the current time.

    Raises :class:`FeedDecodeError` if the payload is not a valid FeedMessage.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    try:
        feed.ParseFromString(payload)
    except DecodeError as exc:
        raise FeedDecodeError(f"invalid protobuf payload: {exc}") from exc

    header_ts = (
        datetime.fromtimestamp(feed.header.timestamp, UTC) if feed.header.timestamp else None
    )
    default_ts = header_ts or fallback_timestamp or datetime.now(UTC)

    positions: list[VehiclePosition] = []
    for entity in feed.entity:
        if not entity.HasField("vehicle") or not entity.vehicle.HasField("position"):
            logger.warning("skipping feed entity %s without vehicle position", entity.id)
            continue
        vehicle = entity.vehicle
        vehicle_id = vehicle.vehicle.id or entity.id
        if not vehicle_id:
            logger.warning("skipping feed entity with no vehicle id")
            continue
        timestamp = (
            datetime.fromtimestamp(vehicle.timestamp, UTC) if vehicle.timestamp else default_ts
        )
        positions.append(
            VehiclePosition(
                vehicle_id=vehicle_id,
                latitude=vehicle.position.latitude,
                longitude=vehicle.position.longitude,
                timestamp=timestamp,
                trip_id=vehicle.trip.trip_id or None,
                route_id=vehicle.trip.route_id or None,
                bearing=vehicle.position.bearing if vehicle.position.HasField("bearing") else None,
                speed_mps=vehicle.position.speed if vehicle.position.HasField("speed") else None,
                label=vehicle.vehicle.label or None,
                current_status=(
                    _STATUS_BY_NUMBER.get(vehicle.current_status)
                    if vehicle.HasField("current_status")
                    else None
                ),
                current_stop_id=vehicle.stop_id or None,
                source="realtime_gps",
            )
        )
    return positions
