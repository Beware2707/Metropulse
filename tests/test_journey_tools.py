"""Tests for the timetable tools: latest departure, reach, meet."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from gtfs_fixture import write_multiline_gtfs_zip
from metropulse.application.commuter.last_train import LastTrainService
from metropulse.application.journey_planner import JourneyPlanner
from metropulse.application.journey_tools import JourneyTools
from metropulse.application.static_loader import GtfsStaticLoader
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.models import Base

# A weekday well inside the fixture calendar (WK runs daily through 2026,
# except the 2026-08-15 calendar_dates removal).
SERVICE_DATE = date(2026, 7, 1)


@pytest.fixture
def tools(loaded_session_factory: SessionFactory) -> JourneyTools:
    """Journey tools over the single-line fixture dataset."""
    return JourneyTools(JourneyPlanner(loaded_session_factory), LastTrainService())


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


# --- latest departure --------------------------------------------------------


async def test_latest_departure_matches_last_feasible_trip(
    tools: JourneyTools, loaded_session_factory: SessionFactory
) -> None:
    # Fixture stop_times: T1 (the only S1->S4 trip) departs S1 at 08:00:30
    # and arrives S4 at 08:09:00, so that IS the last feasible departure.
    async with loaded_session_factory() as session:
        plan = await tools.latest_departure(session, "S1", "S4", on_date=SERVICE_DATE)

    assert plan is not None
    assert plan.origin == "S1" and plan.destination == "S4"
    assert plan.depart_by.isoformat() == "2026-07-01T08:00:30+05:30"
    assert plan.arrive_by.isoformat() == "2026-07-01T08:09:00+05:30"
    assert plan.total_minutes == 9  # ceil(510 s / 60)
    assert len(plan.legs) == 1
    leg = plan.legs[0]
    assert leg.route_long_name == "Red Line"
    assert leg.route_color == "EE1C25"
    assert leg.board_stop_id == "S1" and leg.board_name == "Alpha"
    assert leg.alight_stop_id == "S4" and leg.alight_name == "Delta"
    assert leg.headsign == "Towards Delta"
    assert leg.last_departure == plan.depart_by


async def test_latest_departure_reverse_direction_uses_inbound_trip(
    tools: JourneyTools, loaded_session_factory: SessionFactory
) -> None:
    # T2 departs S4 at 09:00:30 and arrives S1 at 09:09:00.
    async with loaded_session_factory() as session:
        plan = await tools.latest_departure(session, "S4", "S1", on_date=SERVICE_DATE)

    assert plan is not None
    assert plan.depart_by.isoformat() == "2026-07-01T09:00:30+05:30"
    assert plan.arrive_by.isoformat() == "2026-07-01T09:09:00+05:30"
    assert plan.legs[0].headsign == "Towards Alpha"


async def test_latest_departure_none_when_service_removed(
    tools: JourneyTools, loaded_session_factory: SessionFactory
) -> None:
    # calendar_dates removes WK on 2026-08-15, so no trips run at all.
    async with loaded_session_factory() as session:
        plan = await tools.latest_departure(
            session, "S1", "S4", on_date=date(2026, 8, 15)
        )
    assert plan is None


async def test_latest_departure_backward_pass_respects_interchange(
    multiline_session_factory: SessionFactory,
) -> None:
    tools = JourneyTools(JourneyPlanner(multiline_session_factory), LastTrainService())

    # X3 -> S1 chains TB2 (dep X3 09:00:30, arr X2 09:03:00), a ~197 s walk
    # X2 -> S2, then T2 (dep S2 09:06:30, arr S1 09:09:00): feasible.
    async with multiline_session_factory() as session:
        plan = await tools.latest_departure(session, "X3", "S1", on_date=SERVICE_DATE)
    assert plan is not None
    assert [leg.board_stop_id for leg in plan.legs] == ["X3", "S2"]
    assert plan.legs[0].last_departure.isoformat() == "2026-07-01T09:00:30+05:30"
    assert plan.legs[1].last_departure.isoformat() == "2026-07-01T09:06:30+05:30"
    assert plan.depart_by == plan.legs[0].last_departure
    assert plan.arrive_by.isoformat() == "2026-07-01T09:09:00+05:30"

    # S1 -> X3 cannot complete: T1 reaches the S2/X2 walk at 08:03:00 but the
    # only Blue trip leaves X2 at 08:02:30, so no same-day chain exists.
    async with multiline_session_factory() as session:
        infeasible = await tools.latest_departure(
            session, "S1", "X3", on_date=SERVICE_DATE
        )
    assert infeasible is None


async def test_latest_departure_unknown_stop_raises(
    tools: JourneyTools, loaded_session_factory: SessionFactory
) -> None:
    async with loaded_session_factory() as session:
        with pytest.raises(UnknownEntityError):
            await tools.latest_departure(session, "GHOST", "S4", on_date=SERVICE_DATE)


# --- reach --------------------------------------------------------------------


async def test_reach_returns_increasing_minutes_down_the_line(
    tools: JourneyTools,
) -> None:
    # Planner weights: 300 s boarding wait + 150 s per hop, rounded up.
    reach = await tools.reach("S1")
    assert reach == {"S1": 0, "S2": 8, "S3": 10, "S4": 13}
    assert reach["S2"] < reach["S3"] < reach["S4"]


async def test_reach_unknown_origin_raises(tools: JourneyTools) -> None:
    with pytest.raises(UnknownEntityError):
        await tools.reach("GHOST")


# --- meet -----------------------------------------------------------------------


async def test_meet_ranks_middle_stop_first(
    tools: JourneyTools, loaded_session_factory: SessionFactory
) -> None:
    async with loaded_session_factory() as session:
        candidates = await tools.meet(session, "S1", "S4")

    assert [c.stop_id for c in candidates] == ["S2", "S3", "S1", "S4"]
    first = candidates[0]
    assert first.name == "Bravo"
    assert first.minutes_a == 8 and first.minutes_b == 10
    assert first.max_minutes == 10 and first.total_minutes == 18
    # Fairness first: endpoints have a lower total (13) but a higher max (13).
    assert candidates[-1].max_minutes > first.max_minutes


async def test_meet_unknown_stop_raises(
    tools: JourneyTools, loaded_session_factory: SessionFactory
) -> None:
    async with loaded_session_factory() as session:
        with pytest.raises(UnknownEntityError):
            await tools.meet(session, "GHOST", "S4")


# --- API ------------------------------------------------------------------------


async def test_latest_departure_api(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/journeys/latest-departure",
        params={"origin": "S1", "destination": "S4"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["origin"] == "S1" and body["destination"] == "S4"
    assert body["depart_by"].endswith("T08:00:30+05:30")
    assert body["arrive_by"].endswith("T08:09:00+05:30")
    assert body["total_minutes"] == 9
    assert len(body["legs"]) == 1
    leg = body["legs"][0]
    assert leg["route_long_name"] == "Red Line"
    assert leg["route_color"] == "EE1C25"
    assert leg["board_stop_id"] == "S1" and leg["board_name"] == "Alpha"
    assert leg["alight_stop_id"] == "S4" and leg["alight_name"] == "Delta"
    assert leg["headsign"] == "Towards Delta"
    assert leg["last_departure"] == body["depart_by"]

    unknown = await api_client.get(
        "/api/v1/journeys/latest-departure",
        params={"origin": "GHOST", "destination": "S4"},
    )
    assert unknown.status_code == 404

    same = await api_client.get(
        "/api/v1/journeys/latest-departure",
        params={"origin": "S1", "destination": "S1"},
    )
    assert same.status_code == 404


async def test_reach_api(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/journeys/reach",
        params={"origin": "S1", "at": "2026-07-01T08:00:00+05:30"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["origin"] == "S1"
    assert body["at"] == "2026-07-01T08:00:00+05:30"
    assert body["reach"] == {"S1": 0, "S2": 8, "S3": 10, "S4": 13}

    default_at = await api_client.get(
        "/api/v1/journeys/reach", params={"origin": "S1"}
    )
    assert default_at.status_code == 200
    assert default_at.json()["reach"] == body["reach"]

    unknown = await api_client.get(
        "/api/v1/journeys/reach", params={"origin": "GHOST"}
    )
    assert unknown.status_code == 404


async def test_meet_api(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/journeys/meet", params={"a": "S1", "b": "S4"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["a"] == "S1" and body["b"] == "S4"
    assert [c["stop_id"] for c in body["candidates"]] == ["S2", "S3", "S1", "S4"]
    first = body["candidates"][0]
    assert first == {
        "stop_id": "S2",
        "name": "Bravo",
        "minutes_a": 8,
        "minutes_b": 10,
        "max_minutes": 10,
        "total_minutes": 18,
    }

    unknown = await api_client.get(
        "/api/v1/journeys/meet", params={"a": "GHOST", "b": "S4"}
    )
    assert unknown.status_code == 404
