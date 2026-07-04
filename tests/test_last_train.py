"""Tests for service calendars, last-train computation and reminders."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from metropulse.application.commuter.journeys import JourneyService
from metropulse.application.commuter.last_train import LastTrainService
from metropulse.application.commuter.notifications import NotificationService
from metropulse.application.commuter.rule_engine import CommuterRuleEngine
from metropulse.application.eta_engine import EtaEngine, EtaParameters
from metropulse.application.route_resolver import RouteResolver
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import LastTrainReminder
from metropulse.infrastructure.db.commuter_repositories import (
    LastTrainReminderRepository,
    NotificationRepository,
)
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore
from metropulse.wiring import AppResources

IST = ZoneInfo("Asia/Kolkata")
# A regular weekday inside the fixture calendar (WK runs every day of 2026).
SERVICE_DATE = date(2026, 7, 6)
# The fixture's service exception removes WK on Independence Day.
EXCEPTION_DATE = date(2026, 8, 15)


@pytest.fixture
def service() -> LastTrainService:
    return LastTrainService(timezone="Asia/Kolkata")


async def test_active_services_follow_calendar_and_exceptions(
    loaded_session_factory: SessionFactory, service: LastTrainService
) -> None:
    async with loaded_session_factory() as session:
        assert await service.active_service_ids(session, SERVICE_DATE) == {"WK"}
        assert await service.active_service_ids(session, EXCEPTION_DATE) == set()
        assert await service.active_service_ids(session, date(2030, 1, 1)) == set()


async def test_last_departure_excludes_terminal_stops(
    loaded_session_factory: SessionFactory, service: LastTrainService
) -> None:
    async with loaded_session_factory() as session:
        # At S2 the latest boardable departure is T2 (09:06:30); T1 leaves
        # earlier (08:03:30).
        info = await service.last_departure(session, "S2", SERVICE_DATE)
        assert info is not None
        assert info.trip_id == "T2"
        assert info.departure_seconds == 9 * 3600 + 6 * 60 + 30
        assert info.departure_at == datetime(2026, 7, 6, 9, 6, 30, tzinfo=IST)

        # At S1 the only boardable departure is T1 (T2 terminates there).
        s1 = await service.last_departure(session, "S1", SERVICE_DATE)
        assert s1 is not None
        assert s1.trip_id == "T1"


async def test_last_departure_respects_route_and_direction_filters(
    loaded_session_factory: SessionFactory, service: LastTrainService
) -> None:
    async with loaded_session_factory() as session:
        outbound = await service.last_departure(
            session, "S2", SERVICE_DATE, direction_id=0
        )
        assert outbound is not None
        assert outbound.trip_id == "T1"
        none = await service.last_departure(
            session, "S2", SERVICE_DATE, route_id="GHOST"
        )
        assert none is None


async def test_no_departure_on_exception_day(
    loaded_session_factory: SessionFactory, service: LastTrainService
) -> None:
    async with loaded_session_factory() as session:
        assert await service.last_departure(session, "S2", EXCEPTION_DATE) is None


async def _add_reminder(
    resources: AppResources, stop_id: str, lead_minutes: int
) -> tuple[str, int]:
    async with resources.session_factory() as session:
        async with session.begin():
            user, _, _ = await resources.commuter.users.register(session, "lt-dev", None)
            reminder = LastTrainReminder(
                user_id=user.id,
                stop_id=stop_id,
                route_id=None,
                direction_id=None,
                lead_minutes=lead_minutes,
                enabled=True,
                created_at=utcnow(),
            )
            LastTrainReminderRepository(session).add(reminder)
            await session.flush()
            return user.id, reminder.id


def _rule_engine(
    resources: AppResources,
    store: RedisVehicleStore,
    resolver: RouteResolver,
) -> CommuterRuleEngine:
    return CommuterRuleEngine(
        store,
        resolver,
        EtaEngine(resources.session_factory, EtaParameters()),
        resources.session_factory,
        NotificationService(),
        LastTrainService(),
        JourneyService(),
    )


async def test_reminder_fires_inside_window_and_only_once(
    resources: AppResources, store: RedisVehicleStore, resolver: RouteResolver
) -> None:
    user_id, reminder_id = await _add_reminder(resources, "S2", lead_minutes=30)
    engine = _rule_engine(resources, store, resolver)
    departure = datetime(2026, 7, 6, 9, 6, 30, tzinfo=IST)

    # 10 minutes before the last train: inside the 30-minute window.
    sent = await engine.evaluate_reminders(now=departure - timedelta(minutes=10))
    assert sent == 1
    async with resources.session_factory() as session:
        notifications = await NotificationRepository(session).list_for_user(user_id)
        assert len(notifications) == 1
        assert notifications[0].kind == "last_train"
        reminder = await LastTrainReminderRepository(session).get(reminder_id)
        assert reminder is not None
        assert reminder.last_notified_service_date == SERVICE_DATE

    # Same service day again: deduplicated.
    again = await engine.evaluate_reminders(now=departure - timedelta(minutes=5))
    assert again == 0


async def test_reminder_outside_window_does_not_fire(
    resources: AppResources, store: RedisVehicleStore, resolver: RouteResolver
) -> None:
    await _add_reminder(resources, "S2", lead_minutes=30)
    engine = _rule_engine(resources, store, resolver)
    departure = datetime(2026, 7, 6, 9, 6, 30, tzinfo=IST)

    too_early = await engine.evaluate_reminders(now=departure - timedelta(hours=2))
    assert too_early == 0
    too_late = await engine.evaluate_reminders(now=departure + timedelta(minutes=1))
    assert too_late == 0


async def test_last_train_api(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/stations/S2/last-train", params={"date": SERVICE_DATE.isoformat()}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["trip_id"] == "T2"
    assert body["departure_at"].startswith("2026-07-06T09:06:30")

    filtered = await api_client.get(
        "/api/v1/stations/S2/last-train",
        params={"date": SERVICE_DATE.isoformat(), "direction_id": 0},
    )
    assert filtered.json()["trip_id"] == "T1"

    no_service = await api_client.get(
        "/api/v1/stations/S2/last-train", params={"date": EXCEPTION_DATE.isoformat()}
    )
    assert no_service.status_code == 404

    unknown = await api_client.get("/api/v1/stations/GHOST/last-train")
    assert unknown.status_code == 404
