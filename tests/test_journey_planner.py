"""Tests for the journey planner: single line, interchanges, API surface."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from gtfs_fixture import write_multiline_gtfs_zip
from metropulse.application.journey_planner import JourneyPlanner, PlannerParameters
from metropulse.application.static_loader import GtfsStaticLoader
from metropulse.domain.exceptions import NoRouteError, UnknownEntityError
from metropulse.domain.journey import RideLeg, WalkLeg
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.models import Base

PARAMS = PlannerParameters(
    walk_max_m=300.0,
    walk_speed_mps=1.3,
    transfer_overhead_seconds=120.0,
    board_penalty_seconds=300.0,
)


@pytest.fixture
async def multiline_session_factory(tmp_path: Path) -> AsyncIterator[SessionFactory]:
    """A database loaded with the two-line (Red + Blue) fixture."""
    url = f"sqlite+aiosqlite:///{(tmp_path / 'multiline.db').as_posix()}"
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    await GtfsStaticLoader(factory).load(write_multiline_gtfs_zip(tmp_path / "ml.zip"))
    yield factory
    await engine.dispose()


async def test_single_line_plan(loaded_session_factory: SessionFactory) -> None:
    planner = JourneyPlanner(loaded_session_factory, PARAMS)
    plan = await planner.plan("S1", "S4")

    assert plan.interchange_count == 0
    assert plan.walking_distance_m == 0.0
    assert len(plan.legs) == 1
    leg = plan.legs[0]
    assert isinstance(leg, RideLeg)
    assert leg.route_id == "R1"
    assert leg.route_long_name == "Red Line"
    assert leg.route_color == "EE1C25"
    assert leg.direction_id == 0
    assert leg.platform_hint == "Towards Delta"
    assert [s.stop_id for s in leg.stations] == ["S1", "S2", "S3", "S4"]
    # Schedule: 3 hops of 150 s each; total adds one boarding wait.
    assert leg.ride_seconds == pytest.approx(450.0)
    assert plan.expected_travel_seconds == pytest.approx(450.0 + 300.0)
    elapsed = (plan.expected_arrival_at - plan.departure_at).total_seconds()
    assert elapsed == pytest.approx(plan.expected_travel_seconds)
    assert [s.stop_id for s in plan.remaining_stations] == ["S2", "S3", "S4"]


async def test_reverse_direction_uses_opposite_pattern(
    loaded_session_factory: SessionFactory,
) -> None:
    planner = JourneyPlanner(loaded_session_factory, PARAMS)
    plan = await planner.plan("S4", "S1")
    leg = plan.legs[0]
    assert isinstance(leg, RideLeg)
    assert leg.direction_id == 1
    assert leg.platform_hint == "Towards Alpha"
    assert [s.stop_id for s in leg.stations] == ["S4", "S3", "S2", "S1"]


async def test_partial_segment_plan(loaded_session_factory: SessionFactory) -> None:
    planner = JourneyPlanner(loaded_session_factory, PARAMS)
    plan = await planner.plan("S2", "S3")
    leg = plan.legs[0]
    assert isinstance(leg, RideLeg)
    assert [s.stop_id for s in leg.stations] == ["S2", "S3"]


async def test_interchange_plan_with_walking_transfer(
    multiline_session_factory: SessionFactory,
) -> None:
    planner = JourneyPlanner(multiline_session_factory, PARAMS)
    plan = await planner.plan("S1", "X3")

    kinds = [leg.kind for leg in plan.legs]
    assert kinds == ["ride", "walk", "ride"]
    ride1, walk, ride2 = plan.legs
    assert isinstance(ride1, RideLeg) and isinstance(walk, WalkLeg)
    assert isinstance(ride2, RideLeg)
    assert ride1.route_id == "R1"
    assert ride1.alight.stop_id == "S2"
    assert walk.board.stop_id == "S2"
    assert walk.alight.stop_id == "X2"
    assert walk.distance_m == pytest.approx(100, rel=0.1)
    assert ride2.route_id == "B1"
    assert ride2.platform_hint == "Towards South Gate"
    assert [s.stop_id for s in ride2.stations] == ["X2", "X3"]

    assert plan.interchange_count == 1
    assert [s.stop_id for s in plan.interchange_stops] == ["S2"]
    assert plan.walking_distance_m == pytest.approx(100, rel=0.1)


async def test_unknown_stop_raises(loaded_session_factory: SessionFactory) -> None:
    planner = JourneyPlanner(loaded_session_factory, PARAMS)
    with pytest.raises(UnknownEntityError):
        await planner.plan("GHOST", "S4")


async def test_same_origin_destination_raises(
    loaded_session_factory: SessionFactory,
) -> None:
    planner = JourneyPlanner(loaded_session_factory, PARAMS)
    with pytest.raises(NoRouteError):
        await planner.plan("S1", "S1")


async def test_graph_is_cached_per_dataset_version(
    loaded_session_factory: SessionFactory,
) -> None:
    planner = JourneyPlanner(loaded_session_factory, PARAMS)
    first = await planner._get_graph()
    second = await planner._get_graph()
    assert first is second
    await planner.invalidate()
    third = await planner._get_graph()
    assert third is not first


async def test_journey_plan_api(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/journey/plan", params={"origin": "S1", "destination": "S4"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["interchange_count"] == 0
    assert body["interchange_stop_ids"] == []
    assert body["legs"][0]["kind"] == "ride"
    assert body["legs"][0]["route_long_name"] == "Red Line"
    assert [s["stop_id"] for s in body["remaining_stations"]] == ["S2", "S3", "S4"]

    unknown = await api_client.get(
        "/api/v1/journey/plan", params={"origin": "GHOST", "destination": "S4"}
    )
    assert unknown.status_code == 404

    same = await api_client.get(
        "/api/v1/journey/plan", params={"origin": "S1", "destination": "S1"}
    )
    assert same.status_code == 409
