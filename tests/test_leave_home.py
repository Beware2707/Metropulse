"""Tests for leave-home reminders and interchange reminders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
from metropulse.infrastructure.db.commuter_models import LeaveHomeReminder
from metropulse.infrastructure.db.commuter_repositories import (
    JourneyRepository,
    LeaveHomeReminderRepository,
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
    )


async def test_leave_home_api_lifecycle(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    departure = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    created = await api_client.post(
        "/api/v1/me/reminders/leave-home",
        json={
            "stop_id": "S1",
            "train_departure_at": departure,
            "walking_minutes": 12,
            "buffer_minutes": 5,
        },
        headers=auth_headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    notify_at = datetime.fromisoformat(body["notify_at"])
    expected = datetime.fromisoformat(departure) - timedelta(minutes=17)
    assert abs((notify_at - expected).total_seconds()) < 1

    listing = await api_client.get("/api/v1/me/reminders/leave-home", headers=auth_headers)
    assert [r["id"] for r in listing.json()] == [body["id"]]

    deleted = await api_client.delete(
        f"/api/v1/me/reminders/leave-home/{body['id']}", headers=auth_headers
    )
    assert deleted.status_code == 204
    again = await api_client.delete(
        f"/api/v1/me/reminders/leave-home/{body['id']}", headers=auth_headers
    )
    assert again.status_code == 404


async def test_leave_home_in_the_past_rejected(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    departure = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    response = await api_client.post(
        "/api/v1/me/reminders/leave-home",
        json={"stop_id": "S1", "train_departure_at": departure, "walking_minutes": 30},
        headers=auth_headers,
    )
    assert response.status_code == 422

    unknown_stop = await api_client.post(
        "/api/v1/me/reminders/leave-home",
        json={
            "stop_id": "GHOST",
            "train_departure_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            "walking_minutes": 10,
        },
        headers=auth_headers,
    )
    assert unknown_stop.status_code == 404


async def _create_pending_reminder(
    resources: AppResources, notify_at: datetime
) -> tuple[str, int]:
    async with resources.session_factory() as session:
        async with session.begin():
            user, _, _ = await resources.commuter.users.register(session, "lh-dev", None)
            reminder = LeaveHomeReminder(
                user_id=user.id,
                stop_id="S1",
                train_departure_at=notify_at + timedelta(minutes=25),
                walking_minutes=15,
                buffer_minutes=10,
                notify_at=notify_at,
                status="pending",
                created_at=utcnow(),
            )
            LeaveHomeReminderRepository(session).add(reminder)
            await session.flush()
            return user.id, reminder.id


async def test_due_leave_home_reminder_fires_once(
    resources: AppResources, rule_engine: CommuterRuleEngine
) -> None:
    now = utcnow()
    user_id, reminder_id = await _create_pending_reminder(
        resources, notify_at=now - timedelta(seconds=30)
    )

    sent = await rule_engine.evaluate_reminders(now=now)
    assert sent == 1
    async with resources.session_factory() as session:
        reminder = await LeaveHomeReminderRepository(session).get(reminder_id)
        assert reminder is not None
        assert reminder.status == "sent"
        assert reminder.sent_at is not None
        notifications = await NotificationRepository(session).list_for_user(user_id)
        assert [n.kind for n in notifications] == ["leave_home"]

    # Already sent: never fires again.
    assert await rule_engine.evaluate_reminders(now=now + timedelta(minutes=1)) == 0


async def test_future_leave_home_reminder_does_not_fire(
    resources: AppResources, rule_engine: CommuterRuleEngine
) -> None:
    now = utcnow()
    await _create_pending_reminder(resources, notify_at=now + timedelta(hours=1))
    assert await rule_engine.evaluate_reminders(now=now) == 0


async def test_interchange_reminder_fires_once_then_journey_completes(
    resources: AppResources, rule_engine: CommuterRuleEngine
) -> None:
    async with resources.session_factory() as session:
        async with session.begin():
            user, _, _ = await resources.commuter.users.register(session, "ic-dev", None)
            journey = await resources.commuter.journeys.start(
                session, user.id, "S1", "S4",
                vehicle_id="v1", interchange_stop_ids=["S3"],
            )
            journey_id = journey.id

    # Approaching S3 (the planned interchange).
    await resources.vehicle_store.apply(
        {"v1": make_vehicle("v1", longitude=77.015)}, []
    )
    result = await rule_engine.evaluate_realtime()
    assert result.interchange_reminders == 1

    # Same position: already notified, no duplicate.
    second = await rule_engine.evaluate_realtime()
    assert second.interchange_reminders == 0

    async with resources.session_factory() as session:
        notifications = await NotificationRepository(session).list_for_user(user.id)
        kinds = [n.kind for n in notifications]
        assert kinds == ["interchange_reminder"]

    # The train later reaches the destination: journey still auto-completes.
    await resources.vehicle_store.apply(
        {"v1": make_vehicle("v1", longitude=77.03)}, []
    )
    final = await rule_engine.evaluate_realtime()
    assert final.journeys_completed == 1
    async with resources.session_factory() as session:
        journey_row = await JourneyRepository(session).get(journey_id)
        assert journey_row is not None
        assert journey_row.status == "completed"


async def test_journey_start_validates_interchange_stops(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/v1/me/journeys",
        json={
            "origin_stop_id": "S1",
            "destination_stop_id": "S4",
            "interchange_stop_ids": ["GHOST"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 404
