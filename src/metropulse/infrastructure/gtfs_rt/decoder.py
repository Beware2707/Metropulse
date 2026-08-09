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


def _has_fix(latitude: float, longitude: float) -> bool:
    """Whether a coordinate pair is a real fix rather than a null sentinel.

    GTFS-RT declares latitude/longitude ``required``, so a producer with no
    GPS fix cannot omit them — it has to send *something*, and the something
    is almost always 0,0. That point is open ocean in the Gulf of Guinea; no
    transit vehicle is ever there, so treating it as a fix is never right.

    It is also not a harmless glitch downstream: RouteResolver.locate projects
    any position onto the trip shape, so 0,0 does not render as an obvious
    error out at sea — it snaps to whichever end of the line is nearest and
    shows a rider a confident, wrong train.
    """
    if latitude != latitude or longitude != longitude:  # NaN
        return False
    if latitude == 0.0 and longitude == 0.0:
        return False
    return -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0


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
    seen_ids: dict[str, str] = {}  # vehicle_id -> the entity.id that claimed it
    for entity in feed.entity:
        if not entity.HasField("vehicle") or not entity.vehicle.HasField("position"):
            logger.warning("skipping feed entity %s without vehicle position", entity.id)
            continue
        vehicle = entity.vehicle
        vehicle_id = vehicle.vehicle.id or entity.id
        if not vehicle_id:
            logger.warning("skipping feed entity with no vehicle id")
            continue
        if vehicle_id in seen_ids:
            # GTFS-RT guarantees entity.id is unique; it guarantees nothing
            # about vehicle.id. The engine keys its snapshot by vehicle_id, so
            # a collision would silently overwrite one train with another and
            # report the loser as "removed" — a train disappearing off the map
            # with no error anywhere. Keeping the first is arbitrary but
            # deterministic; the point is that this is now LOUD instead of
            # invisible. ERROR, not warning: the feed is malformed and a
            # rider is being shown fewer trains than are running.
            logger.error(
                "duplicate vehicle id %r in feed (entities %s and %s); keeping the "
                "first — the second train will not be shown",
                vehicle_id, seen_ids[vehicle_id], entity.id,
            )
            continue
        if not _has_fix(vehicle.position.latitude, vehicle.position.longitude):
            logger.warning(
                "skipping vehicle %r: no usable position fix (%s, %s)",
                vehicle_id, vehicle.position.latitude, vehicle.position.longitude,
            )
            continue
        seen_ids[vehicle_id] = entity.id
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
