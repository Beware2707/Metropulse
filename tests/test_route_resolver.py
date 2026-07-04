"""Tests for ID mapping and route resolution."""

from __future__ import annotations

import dataclasses

import pytest
from pydantic import ValidationError

from factories import make_vehicle
from metropulse.application.route_resolver import IdMapper, MappingRule, RouteResolver
from metropulse.config import IdMappingRule
from metropulse.infrastructure.db.base import SessionFactory


def test_mapper_exact_candidate_first() -> None:
    mapper = IdMapper()
    assert mapper.candidates("trip_id", "T1") == ["T1"]


def test_mapper_static_map_and_rules_ordered_and_deduped() -> None:
    mapper = IdMapper(
        rules=[
            MappingRule(field="trip_id", pattern="^RT_", replacement=""),
            MappingRule(field="route_id", pattern="_DOWN$", replacement=""),
        ],
        trip_id_map={"RT_T9": "T9-mapped"},
    )
    assert mapper.candidates("trip_id", "RT_T9") == ["RT_T9", "T9-mapped", "T9"]
    # route rules must not apply to trip ids
    assert mapper.candidates("trip_id", "X_DOWN") == ["X_DOWN"]
    assert mapper.candidates("route_id", "R1_DOWN") == ["R1_DOWN", "R1"]


async def test_resolves_exact_trip_id(resolver: RouteResolver) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    assert context.route_id == "R1"
    assert context.route_long_name == "Red Line"
    assert context.headsign == "Towards Delta"
    assert [s.stop_id for s in context.stops] == ["S1", "S2", "S3", "S4"]
    assert context.geometry is not None
    # Distances along the shape must be strictly increasing.
    distances = [s.distance_along_shape_m for s in context.stops]
    assert distances == sorted(distances)
    assert distances[0] < 50


async def test_resolves_prefixed_trip_id_via_rule(
    loaded_session_factory: SessionFactory,
) -> None:
    mapper = IdMapper(rules=[MappingRule(field="trip_id", pattern="^RT_", replacement="")])
    resolver = RouteResolver(loaded_session_factory, mapper)
    context = await resolver.resolve_trip("RT_T1")
    assert context is not None
    assert context.trip_id == "T1"


async def test_unknown_trip_resolves_to_none_and_is_cached(
    resolver: RouteResolver,
) -> None:
    assert await resolver.resolve_trip("GHOST") is None
    assert await resolver.resolve_trip("GHOST") is None  # cached path


async def test_route_fallback_resolution(loaded_session_factory: SessionFactory) -> None:
    mapper = IdMapper(rules=[MappingRule(field="route_id", pattern="_X$", replacement="")])
    resolver = RouteResolver(loaded_session_factory, mapper)
    route = await resolver.resolve_route("R1_X")
    assert route is not None
    assert route.route_id == "R1"
    assert await resolver.resolve_route("NOPE") is None


async def test_locate_at_station(resolver: RouteResolver) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    location = resolver.locate(make_vehicle(longitude=77.01), context)
    assert location.at_station is True
    assert location.current_station is not None
    assert location.current_station.stop_id == "S2"
    assert location.next_station is not None
    assert location.next_station.stop_id == "S3"
    assert location.destination is not None
    assert location.destination.stop_id == "S4"


async def test_locate_between_stations(resolver: RouteResolver) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    location = resolver.locate(make_vehicle(longitude=77.015), context)
    assert location.at_station is False
    assert location.current_station is not None
    assert location.current_station.stop_id == "S2"
    assert location.next_station is not None
    assert location.next_station.stop_id == "S3"
    assert location.shape_offset_m is not None
    assert location.shape_offset_m < 10


async def test_locate_reports_remaining_stations(resolver: RouteResolver) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    # Between S2 and S3: everything from S3 onward remains.
    mid = resolver.locate(make_vehicle(longitude=77.015), context)
    assert [s.stop_id for s in mid.remaining_stations] == ["S3", "S4"]
    # At the origin: everything after S1 remains.
    start = resolver.locate(make_vehicle(longitude=77.0), context)
    assert [s.stop_id for s in start.remaining_stations] == ["S2", "S3", "S4"]
    # At the terminus: nothing remains.
    end = resolver.locate(make_vehicle(longitude=77.03), context)
    assert end.remaining_stations == ()


async def test_locate_at_terminus_has_no_next(resolver: RouteResolver) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    location = resolver.locate(make_vehicle(longitude=77.03), context)
    assert location.at_station is True
    assert location.current_station is not None
    assert location.current_station.stop_id == "S4"
    assert location.next_station is None


async def test_locate_respects_direction(resolver: RouteResolver) -> None:
    context = await resolver.resolve_trip("T2")
    assert context is not None
    location = resolver.locate(make_vehicle(longitude=77.015, trip_id="T2"), context)
    # Inbound trip: travelling towards S1, so the next stop is S2.
    assert location.current_station is not None
    assert location.current_station.stop_id == "S3"
    assert location.next_station is not None
    assert location.next_station.stop_id == "S2"
    assert location.destination is not None
    assert location.destination.stop_id == "S1"


async def test_locate_without_shape_uses_nearest_stop(
    loaded_session_factory: SessionFactory, resolver: RouteResolver
) -> None:
    context = await resolver.resolve_trip("T1")
    assert context is not None
    shapeless = dataclasses.replace(context, geometry=None)
    location = resolver.locate(make_vehicle(longitude=77.011), shapeless)
    assert location.current_station is not None
    assert location.current_station.stop_id == "S2"
    assert location.at_station is False  # ~98 m away with a 75 m radius


async def test_clear_cache_forces_rebuild(resolver: RouteResolver) -> None:
    first = await resolver.resolve_trip("T1")
    resolver.clear_cache()
    second = await resolver.resolve_trip("T1")
    assert first is not None and second is not None
    assert first is not second


def test_configured_mapping_rule_rejects_bad_field() -> None:
    with pytest.raises(ValidationError):
        IdMappingRule(field="nonsense", pattern="a", replacement="b")  # type: ignore[arg-type]
