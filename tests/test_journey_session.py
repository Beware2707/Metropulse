"""Tests for the journey session tracker: missed stops and delay alerts.

Completion, interchange, and timeout behaviour is covered end-to-end in
test_journeys.py / test_leave_home.py through the rule engine; this module
exercises the session-specific additions.
"""

from __future__ import annotations

from typing import Any

import pytest

from factories import make_vehicle
from metropulse.application.commuter.journey_session import JourneySessionTracker
from metropulse.application.commuter.journeys import JourneyService
from metropulse.application.commuter.notifications import NotificationService
from metropulse.application.eta_engine import EtaEngine, EtaParameters
from metropulse.application.route_resolver import RouteResolver
from metropulse.domain.entities import VehicleEta, utcnow
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_repositories import (
    JourneyRepository,
    NotificationRepository,
)
from metropulse.wiring import AppResources


class FixedDelayEtaEngine:
    """ETA engine stub reporting a constant arrival delay."""

    def __init__(self, delay_seconds: float | None) -> None:
        self.delay_seconds = delay_seconds

    async def compute(self, vehicle: Any, context: Any) -> VehicleEta:
        return VehicleEta(
            vehicle_id=vehicle.vehicle_id,
            trip_id=context.trip_id,
            computed_at=utcnow(),
            speed_mps_used=10.0,
            speed_source="reported",
            confidence="high",
            stations=(),
            delay_seconds=self.delay_seconds,
        )


def _tracker(
    resolver: RouteResolver,
    session_factory: SessionFactory,
    journeys: JourneyService,
    eta_engine: Any = None,
    delay_notify_seconds: float = 300.0,
) -> JourneySessionTracker:
    return JourneySessionTracker(
        resolver,
        eta_engine or EtaEngine(session_factory, EtaParameters()),
        journeys,
        NotificationService(),
        delay_notify_seconds=delay_notify_seconds,
    )


async def _start_journey(
    resources: AppResources, destination: str, device: str = "js-dev"
) -> tuple[str, int]:
    async with resources.session_factory() as session:
        async with session.begin():
            user, _, _ = await resources.commuter.users.register(session, device, None)
            journey = await resources.commuter.journeys.start(
                session, user.id, "S1", destination, vehicle_id="v1"
            )
            return user.id, journey.id


async def test_missed_stop_detected_and_notified(
    resources: AppResources, resolver: RouteResolver
) -> None:
    user_id, journey_id = await _start_journey(resources, destination="S2")
    tracker = _tracker(resolver, resources.session_factory, resources.commuter.journeys)
    # The train is standing at S4 — it sailed straight past S2.
    snapshot = {"v1": make_vehicle("v1", longitude=77.03)}

    async with resources.session_factory() as session:
        async with session.begin():
            journey = await JourneyRepository(session).get(journey_id)
            assert journey is not None
            outcome = await tracker.evaluate(session, journey, snapshot)

    assert outcome == "missed"
    async with resources.session_factory() as session:
        journey = await JourneyRepository(session).get(journey_id)
        assert journey is not None
        assert journey.status == "missed"
        events = await JourneyRepository(session).events_for(journey_id)
        assert [e.event_type for e in events] == ["started", "missed"]
        notifications = await NotificationRepository(session).list_for_user(user_id)
        assert [n.kind for n in notifications] == ["missed_stop"]


async def test_arrival_beats_missed_detection(
    resources: AppResources, resolver: RouteResolver
) -> None:
    _, journey_id = await _start_journey(resources, destination="S4")
    tracker = _tracker(resolver, resources.session_factory, resources.commuter.journeys)
    snapshot = {"v1": make_vehicle("v1", longitude=77.03)}  # exactly at S4

    async with resources.session_factory() as session:
        async with session.begin():
            journey = await JourneyRepository(session).get(journey_id)
            assert journey is not None
            outcome = await tracker.evaluate(session, journey, snapshot)
    assert outcome == "completed"


async def test_en_route_is_not_missed(
    resources: AppResources, resolver: RouteResolver
) -> None:
    _, journey_id = await _start_journey(resources, destination="S4")
    tracker = _tracker(resolver, resources.session_factory, resources.commuter.journeys)
    snapshot = {"v1": make_vehicle("v1", longitude=77.015, speed_mps=10.0)}

    async with resources.session_factory() as session:
        async with session.begin():
            journey = await JourneyRepository(session).get(journey_id)
            assert journey is not None
            outcome = await tracker.evaluate(session, journey, snapshot)
    # No delay (schedule-dependent -> stubbed elsewhere), no interchange: None.
    assert outcome in (None, "delay")


async def test_delay_notification_fires_once(
    resources: AppResources, resolver: RouteResolver
) -> None:
    user_id, journey_id = await _start_journey(resources, destination="S4")
    tracker = _tracker(
        resolver,
        resources.session_factory,
        resources.commuter.journeys,
        eta_engine=FixedDelayEtaEngine(delay_seconds=600.0),
        delay_notify_seconds=300.0,
    )
    snapshot = {"v1": make_vehicle("v1", longitude=77.015)}

    async with resources.session_factory() as session:
        async with session.begin():
            journey = await JourneyRepository(session).get(journey_id)
            assert journey is not None
            first = await tracker.evaluate(session, journey, snapshot)
    assert first == "delay"

    async with resources.session_factory() as session:
        async with session.begin():
            journey = await JourneyRepository(session).get(journey_id)
            assert journey is not None
            second = await tracker.evaluate(session, journey, snapshot)
    assert second is None  # notified once per journey

    async with resources.session_factory() as session:
        notifications = await NotificationRepository(session).list_for_user(user_id)
        delays = [n for n in notifications if n.kind == "journey_delay"]
        assert len(delays) == 1
        assert delays[0].payload is not None
        assert delays[0].payload["delay_seconds"] == pytest.approx(600.0)
        journey = await JourneyRepository(session).get(journey_id)
        assert journey is not None
        assert journey.status == "active"  # a late train doesn't end the session


async def test_small_delay_stays_quiet(
    resources: AppResources, resolver: RouteResolver
) -> None:
    _, journey_id = await _start_journey(resources, destination="S4")
    tracker = _tracker(
        resolver,
        resources.session_factory,
        resources.commuter.journeys,
        eta_engine=FixedDelayEtaEngine(delay_seconds=60.0),
        delay_notify_seconds=300.0,
    )
    snapshot = {"v1": make_vehicle("v1", longitude=77.015)}
    async with resources.session_factory() as session:
        async with session.begin():
            journey = await JourneyRepository(session).get(journey_id)
            assert journey is not None
            outcome = await tracker.evaluate(session, journey, snapshot)
    assert outcome is None
