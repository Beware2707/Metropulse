"""Tests for destination alerts: API lifecycle and worker rule evaluation."""

from __future__ import annotations

import httpx
import pytest

from factories import make_vehicle
from metropulse.application.commuter.journeys import JourneyService
from metropulse.application.commuter.last_train import LastTrainService
from metropulse.application.commuter.notifications import NotificationService
from metropulse.application.commuter.rule_engine import CommuterRuleEngine
from metropulse.application.eta_engine import EtaEngine, EtaParameters
from metropulse.application.route_resolver import RouteResolver
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_repositories import (
    DestinationAlertRepository,
    NotificationRepository,
)
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


async def _register_and_alert(
    api_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    resources: AppResources,
    threshold_seconds: int = 120,
) -> dict:
    await resources.vehicle_store.apply({"v1": make_vehicle("v1")}, [])
    response = await api_client.post(
        "/api/v1/me/alerts/destination",
        json={"vehicle_id": "v1", "target_stop_id": "S4",
              "threshold_seconds": threshold_seconds},
        headers=auth_headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_create_list_cancel(
    api_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    resources: AppResources,
) -> None:
    created = await _register_and_alert(api_client, auth_headers, resources)
    assert created["status"] == "active"

    listing = await api_client.get("/api/v1/me/alerts/destination", headers=auth_headers)
    assert [a["id"] for a in listing.json()] == [created["id"]]

    cancel = await api_client.delete(
        f"/api/v1/me/alerts/destination/{created['id']}", headers=auth_headers
    )
    assert cancel.status_code == 204
    # Cancelling twice fails: no longer active.
    again = await api_client.delete(
        f"/api/v1/me/alerts/destination/{created['id']}", headers=auth_headers
    )
    assert again.status_code == 404


async def test_create_rejects_unknown_stop_and_untracked_vehicle(
    api_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    resources: AppResources,
) -> None:
    await resources.vehicle_store.apply({"v1": make_vehicle("v1")}, [])
    unknown_stop = await api_client.post(
        "/api/v1/me/alerts/destination",
        json={"vehicle_id": "v1", "target_stop_id": "GHOST"},
        headers=auth_headers,
    )
    assert unknown_stop.status_code == 404

    untracked = await api_client.post(
        "/api/v1/me/alerts/destination",
        json={"vehicle_id": "ghost-train", "target_stop_id": "S4"},
        headers=auth_headers,
    )
    assert untracked.status_code == 409


async def _create_alert_directly(
    resources: AppResources, vehicle_id: str, target: str, threshold: int
) -> tuple[str, int]:
    """Create a user + alert via services; returns (user_id, alert_id)."""
    async with resources.session_factory() as session:
        async with session.begin():
            user, _, _ = await resources.commuter.users.register(session, "alert-dev", None)
            alert = await resources.commuter.destination_alerts.create(
                session, user.id, vehicle_id, target, threshold
            )
            return user.id, alert.id


async def test_rule_engine_triggers_when_close(
    resources: AppResources, rule_engine: CommuterRuleEngine
) -> None:
    # Train just before S3, alerting on S4 (~1 km away, ~100 s at 10 m/s).
    await resources.vehicle_store.apply(
        {"v1": make_vehicle("v1", longitude=77.021, speed_mps=10.0)}, []
    )
    user_id, alert_id = await _create_alert_directly(resources, "v1", "S4", 300)

    result = await rule_engine.evaluate_realtime()

    assert result.alerts_triggered == 1
    async with resources.session_factory() as session:
        alert = await DestinationAlertRepository(session).get(alert_id)
        assert alert is not None
        assert alert.status == "triggered"
        assert alert.triggered_at is not None
        notifications = await NotificationRepository(session).list_for_user(user_id)
        assert len(notifications) == 1
        assert notifications[0].kind == "destination_alert"

    # A triggered alert is not evaluated again.
    second = await rule_engine.evaluate_realtime()
    assert second.alerts_triggered == 0


async def test_rule_engine_leaves_far_alert_active(
    resources: AppResources, rule_engine: CommuterRuleEngine
) -> None:
    await resources.vehicle_store.apply(
        {"v1": make_vehicle("v1", longitude=77.001, speed_mps=10.0)}, []
    )
    _, alert_id = await _create_alert_directly(resources, "v1", "S4", 30)

    result = await rule_engine.evaluate_realtime()

    assert result.alerts_triggered == 0
    async with resources.session_factory() as session:
        alert = await DestinationAlertRepository(session).get(alert_id)
        assert alert is not None
        assert alert.status == "active"


async def test_rule_engine_expires_alert_for_vanished_vehicle(
    resources: AppResources, rule_engine: CommuterRuleEngine
) -> None:
    await resources.vehicle_store.apply({"v1": make_vehicle("v1")}, [])
    _, alert_id = await _create_alert_directly(resources, "v1", "S4", 120)
    # The vehicle drops out of the feed.
    await resources.vehicle_store.apply({}, ["v1"])

    result = await rule_engine.evaluate_realtime()

    assert result.alerts_expired == 1
    async with resources.session_factory() as session:
        alert = await DestinationAlertRepository(session).get(alert_id)
        assert alert is not None
        assert alert.status == "expired"
