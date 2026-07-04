"""Tests for the GTFS-RT protobuf decoder."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from google.transit import gtfs_realtime_pb2

from factories import build_feed_payload, make_vehicle
from metropulse.domain.entities import VehicleStopStatus
from metropulse.domain.exceptions import FeedDecodeError
from metropulse.infrastructure.gtfs_rt.decoder import decode_vehicle_positions


def test_decodes_full_entity() -> None:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1_700_000_000
    entity = feed.entity.add()
    entity.id = "e1"
    vp = entity.vehicle
    vp.vehicle.id = "v1"
    vp.vehicle.label = "Train 1"
    vp.trip.trip_id = "T1"
    vp.trip.route_id = "R1"
    vp.position.latitude = 28.6
    vp.position.longitude = 77.0
    vp.position.speed = 12.5
    vp.position.bearing = 90.0
    vp.timestamp = 1_700_000_100
    vp.current_status = gtfs_realtime_pb2.VehiclePosition.STOPPED_AT
    vp.stop_id = "S2"

    positions = decode_vehicle_positions(feed.SerializeToString())
    assert len(positions) == 1
    position = positions[0]
    assert position.vehicle_id == "v1"
    assert position.trip_id == "T1"
    assert position.route_id == "R1"
    assert position.latitude == pytest.approx(28.6)
    assert position.speed_mps == pytest.approx(12.5)
    assert position.bearing == pytest.approx(90.0)
    assert position.label == "Train 1"
    assert position.current_status is VehicleStopStatus.STOPPED_AT
    assert position.current_stop_id == "S2"
    assert position.timestamp == datetime.fromtimestamp(1_700_000_100, UTC)


def test_skips_entities_without_vehicle_or_position() -> None:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    empty = feed.entity.add()
    empty.id = "no-vehicle"
    no_position = feed.entity.add()
    no_position.id = "no-position"
    no_position.vehicle.vehicle.id = "vx"

    assert decode_vehicle_positions(feed.SerializeToString()) == []


def test_falls_back_to_entity_id_when_vehicle_id_missing() -> None:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    entity = feed.entity.add()
    entity.id = "entity-7"
    entity.vehicle.position.latitude = 28.6
    entity.vehicle.position.longitude = 77.0

    positions = decode_vehicle_positions(feed.SerializeToString())
    assert positions[0].vehicle_id == "entity-7"


def test_uses_header_timestamp_when_entity_has_none() -> None:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1_700_000_000
    entity = feed.entity.add()
    entity.id = "e1"
    entity.vehicle.vehicle.id = "v1"
    entity.vehicle.position.latitude = 28.6
    entity.vehicle.position.longitude = 77.0

    positions = decode_vehicle_positions(feed.SerializeToString())
    assert positions[0].timestamp == datetime.fromtimestamp(1_700_000_000, UTC)


def test_optional_fields_default_to_none() -> None:
    payload = build_feed_payload([make_vehicle(speed_mps=None)])
    position = decode_vehicle_positions(payload)[0]
    assert position.speed_mps is None
    assert position.bearing is None
    assert position.current_status is None


def test_invalid_payload_raises() -> None:
    with pytest.raises(FeedDecodeError):
        decode_vehicle_positions(b"\xff\xfe not a protobuf")
