"""Tests for ID mapping and route resolution."""

from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from factories import make_vehicle
from metropulse.application.route_resolver import IdMapper, MappingRule, RouteResolver
from metropulse.config import IdMappingRule, Settings
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.wiring import build_id_mapper


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


async def test_concurrent_misses_share_one_build(resolver: RouteResolver) -> None:
    builds = {"count": 0}
    original = resolver._build_context

    async def counting_build(trip_id: str):  # noqa: ANN202
        builds["count"] += 1
        await asyncio.sleep(0.05)  # widen the race window
        return await original(trip_id)

    resolver._build_context = counting_build  # type: ignore[method-assign]
    results = await asyncio.gather(*(resolver.resolve_trip("T1") for _ in range(10)))

    assert builds["count"] == 1  # single-flight: one build for ten callers
    assert all(r is results[0] for r in results)


async def test_clear_cache_forces_rebuild(resolver: RouteResolver) -> None:
    first = await resolver.resolve_trip("T1")
    resolver.clear_cache()
    second = await resolver.resolve_trip("T1")
    assert first is not None and second is not None
    assert first is not second


def test_configured_mapping_rule_rejects_bad_field() -> None:
    with pytest.raises(ValidationError):
        IdMappingRule(field="nonsense", pattern="a", replacement="b")  # type: ignore[arg-type]


async def test_multi_agency_support_via_configuration_only(
    loaded_session_factory: SessionFactory, tmp_path: Path
) -> None:
    """Two agencies with different realtime ID conventions, zero code changes.

    Agency A prefixes realtime IDs ('DMRC:trip:T1') — solved by a regex rule.
    Agency B uses opaque numeric IDs ('90001') — solved by an explicit map.
    Both are plain JSON profiles fed through Settings -> build_id_mapper.
    """
    agency_a = tmp_path / "agency_a.json"
    agency_a.write_text(
        json.dumps({"rules": [
            {"field": "trip_id", "pattern": "^DMRC:trip:", "replacement": ""},
            {"field": "route_id", "pattern": "^DMRC:route:", "replacement": ""},
        ]}),
        encoding="utf-8",
    )
    agency_b = tmp_path / "agency_b.json"
    agency_b.write_text(
        json.dumps({"trip_id": {"90001": "T1"}, "route_id": {"77": "R1"}}),
        encoding="utf-8",
    )

    resolver_a = RouteResolver(
        loaded_session_factory,
        build_id_mapper(Settings(_env_file=None, id_mapping_file=agency_a)),
    )
    resolver_b = RouteResolver(
        loaded_session_factory,
        build_id_mapper(Settings(_env_file=None, id_mapping_file=agency_b)),
    )

    context_a = await resolver_a.resolve_trip("DMRC:trip:T1")
    assert context_a is not None and context_a.trip_id == "T1"
    route_a = await resolver_a.resolve_route("DMRC:route:R1")
    assert route_a is not None and route_a.route_id == "R1"

    context_b = await resolver_b.resolve_trip("90001")
    assert context_b is not None and context_b.trip_id == "T1"
    route_b = await resolver_b.resolve_route("77")
    assert route_b is not None and route_b.route_id == "R1"

    # Neither profile understands the other's convention.
    assert await resolver_a.resolve_trip("90001") is None
    assert await resolver_b.resolve_trip("DMRC:trip:T1") is None
