"""Tests for journey tracking: API lifecycle and worker auto-completion."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from factories import make_vehicle
from metropulse.application.commuter.journeys import JourneyService
from metropulse.application.commuter.last_train import LastTrainService
from metropulse.application.commuter.notifications import NotificationService
from metropulse.application.commuter.rule_engine import CommuterRuleEngine
from metropulse.application.eta_engine import EtaEngine, EtaParameters
from metropulse.application.route_resolver import RouteResolver
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import Journey
from metropulse.infrastructure.db.commuter_repositories import JourneyRepository
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore
from metropulse.wiring import AppResources


@pytest.fixture
def rule_engine(
    store: RedisVehicleStore,
    loaded_session_factory: SessionFactory,
    resolver: RouteResolver,
) -> CommuterRuleEngine:
    return CommuterRuleEngine(
        store,
        resolver,
        EtaEngine(loaded_session_factory, EtaParameters()),
        loaded_session_factory,
        NotificationService(),
        LastTrainService(),
        JourneyService(),
        journey_max_age_hours=6.0,
    )


async def test_journey_lifecycle_via_api(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    start = await api_client.post(
        "/api/v1/me/journeys",
        json={"origin_stop_id": "S1", "destination_stop_id": "S4", "vehicle_id": "v1"},
        headers=auth_headers,
    )
    assert start.status_code == 201
    journey = start.json()
    assert journey["status"] == "active"

    current = await api_client.get("/api/v1/me/journeys/current", headers=auth_headers)
    assert current.status_code == 200
    assert current.json()["id"] == journey["id"]

    complete = await api_client.post(
        f"/api/v1/me/journeys/{journey['id']}/complete", headers=auth_headers
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"

    no_current = await api_client.get("/api/v1/me/journeys/current", headers=auth_headers)
    assert no_current.status_code == 404

    history = await api_client.get("/api/v1/me/journeys", headers=auth_headers)
    assert history.json()["count"] == 1


async def test_starting_new_journey_supersedes_active(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    first = (
        await api_client.post(
            "/api/v1/me/journeys",
            json={"origin_stop_id": "S1", "destination_stop_id": "S4"},
            headers=auth_headers,
        )
    ).json()
    second = (
        await api_client.post(
            "/api/v1/me/journeys",
            json={"origin_stop_id": "S2", "destination_stop_id": "S3"},
            headers=auth_headers,
        )
    ).json()

    history = (await api_client.get("/api/v1/me/journeys", headers=auth_headers)).json()
    by_id = {j["id"]: j for j in history["journeys"]}
    assert by_id[first["id"]]["status"] == "abandoned"
    assert by_id[second["id"]]["status"] == "active"


async def test_journey_validation(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    same = await api_client.post(
        "/api/v1/me/journeys",
        json={"origin_stop_id": "S1", "destination_stop_id": "S1"},
        headers=auth_headers,
    )
    assert same.status_code == 422

    unknown = await api_client.post(
        "/api/v1/me/journeys",
        json={"origin_stop_id": "S1", "destination_stop_id": "GHOST"},
        headers=auth_headers,
    )
    assert unknown.status_code == 404

    missing = await api_client.post(
        "/api/v1/me/journeys/999999/complete", headers=auth_headers
    )
    assert missing.status_code == 404


async def _start_journey_directly(
    resources: AppResources, vehicle_id: str | None, destination: str
) -> tuple[str, int]:
    async with resources.session_factory() as session:
        async with session.begin():
            user, _, _ = await resources.commuter.users.register(session, "journey-dev", None)
            journey = await resources.commuter.journeys.start(
                session, user.id, "S1", destination, vehicle_id=vehicle_id
            )
            return user.id, journey.id


async def test_rule_engine_auto_completes_on_arrival(
    resources: AppResources, rule_engine: CommuterRuleEngine
) -> None:
    user_id, journey_id = await _start_journey_directly(resources, "v1", "S3")
    # The tracked train is standing at S3 — the journey's destination.
    await resources.vehicle_store.apply({"v1": make_vehicle("v1", longitude=77.02)}, [])

    result = await rule_engine.evaluate_realtime()

    assert result.journeys_completed == 1
    async with resources.session_factory() as session:
        journey = await JourneyRepository(session).get(journey_id)
        assert journey is not None
        assert journey.status == "completed"
        events = await JourneyRepository(session).events_for(journey_id)
        assert [e.event_type for e in events] == ["started", "completed"]
        completed_event = events[-1]
        assert completed_event.payload == {"auto": True}


async def test_rule_engine_leaves_en_route_journey_active(
    resources: AppResources, rule_engine: CommuterRuleEngine
) -> None:
    _, journey_id = await _start_journey_directly(resources, "v1", "S4")
    await resources.vehicle_store.apply(
        {"v1": make_vehicle("v1", longitude=77.015)}, []
    )

    result = await rule_engine.evaluate_realtime()

    assert result.journeys_completed == 0
    async with resources.session_factory() as session:
        journey = await JourneyRepository(session).get(journey_id)
        assert journey is not None
        assert journey.status == "active"


async def test_rule_engine_abandons_stale_journeys(
    resources: AppResources, rule_engine: CommuterRuleEngine
) -> None:
    user_id, journey_id = await _start_journey_directly(resources, None, "S4")
    # Age the journey past the timeout.
    async with resources.session_factory() as session:
        async with session.begin():
            journey = await session.get(Journey, journey_id)
            assert journey is not None
            journey.started_at = utcnow() - timedelta(hours=7)

    result = await rule_engine.evaluate_realtime()

    assert result.journeys_abandoned == 1
    async with resources.session_factory() as session:
        journey = await JourneyRepository(session).get(journey_id)
        assert journey is not None
        assert journey.status == "abandoned"
