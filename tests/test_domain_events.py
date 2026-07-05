"""Tests for typed domain events and the Redis event stream."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import fakeredis.aioredis
import pytest

from factories import make_vehicle
from metropulse.domain import events as ev
from metropulse.infrastructure.redis.event_publisher import (
    EVENTS_STREAM,
    RedisDomainEventPublisher,
)
from metropulse.infrastructure.redis.stream_bus import RedisStreamConsumer
from metropulse.wiring import AppResources

ALL_EVENTS: list[ev.DomainEvent] = [
    ev.VehicleUpdated("v1", "T1", "R1", 28.6, 77.0, "2026-07-05T10:00:00+00:00", "added"),
    ev.VehicleRemoved("v1", "2026-07-05T10:00:05+00:00"),
    ev.EtaUpdated("v1", "T1", "S3", 48.5, 12.0, "2026-07-05T10:00:00+00:00"),
    ev.JourneyStarted(1, "u1", "S1", "S4", "v1", "2026-07-05T10:00:00+00:00"),
    ev.JourneyCompleted(1, "u1", "S4", True, False, "2026-07-05T10:20:00+00:00"),
    ev.ServiceAlertCreated(9, "warning", "R1", None, "Delay", "2026-07-05T10:00:00+00:00"),
    ev.DestinationReached("u1", "v1", "S4", 3, "2026-07-05T10:19:00+00:00"),
]


@pytest.mark.parametrize("event", ALL_EVENTS, ids=[ev.event_name(e) for e in ALL_EVENTS])
def test_events_round_trip(event: ev.DomainEvent) -> None:
    payload = ev.to_payload(event)
    json.dumps(payload)  # must be JSON-serializable as-is
    assert ev.parse_event(payload) == event


def test_unknown_or_malformed_events_parse_to_none() -> None:
    assert ev.parse_event({"event": "FutureEvent", "data": {}}) is None
    assert ev.parse_event({"event": "VehicleRemoved", "data": {"bogus": 1}}) is None
    assert ev.parse_event({"event": "VehicleRemoved"}) is None


async def _read_events(redis: fakeredis.aioredis.FakeRedis) -> list[ev.DomainEvent]:
    entries = await redis.xrange(EVENTS_STREAM)
    parsed = []
    for _, fields in entries:
        event = ev.parse_event(json.loads(fields["data"]))
        if event is not None:
            parsed.append(event)
    return parsed


async def test_publisher_appends_to_event_stream(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    publisher = RedisDomainEventPublisher(fake_redis)
    assert await publisher.publish(ALL_EVENTS[0]) is True
    stored = await _read_events(fake_redis)
    assert stored == [ALL_EVENTS[0]]


async def test_publisher_is_best_effort_on_redis_failure() -> None:
    class BrokenRedis:
        async def xadd(self, *args: Any, **kwargs: Any) -> None:
            raise ConnectionError("redis down")

    publisher = RedisDomainEventPublisher(BrokenRedis())  # type: ignore[arg-type]
    assert await publisher.publish(ALL_EVENTS[0]) is False  # never raises


async def test_consumer_group_receives_typed_events(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    consumer = RedisStreamConsumer(fake_redis, EVENTS_STREAM, "audit", "a1")
    await consumer.ensure_group()
    publisher = RedisDomainEventPublisher(fake_redis)
    received: list[ev.DomainEvent] = []

    async def handler(payload: dict[str, Any]) -> None:
        event = ev.parse_event(payload)
        if event is not None:
            received.append(event)

    task = asyncio.create_task(consumer.run(handler))
    for event in ALL_EVENTS:
        await publisher.publish(event)
    for _ in range(100):
        if len(received) == len(ALL_EVENTS):
            break
        await asyncio.sleep(0.02)
    task.cancel()

    assert received == ALL_EVENTS


async def test_journey_lifecycle_emits_events(resources: AppResources) -> None:
    async with resources.session_factory() as session:
        async with session.begin():
            user, _, _ = await resources.commuter.users.register(session, "ev-dev", None)
            journey = await resources.commuter.journeys.start(
                session, user.id, "S1", "S4", vehicle_id="v1"
            )
    async with resources.session_factory() as session:
        async with session.begin():
            await resources.commuter.journeys.complete(session, user.id, journey.id)

    stored = await _read_events(resources.redis)
    names = [ev.event_name(e) for e in stored]
    assert names == ["JourneyStarted", "JourneyCompleted"]
    started = stored[0]
    assert isinstance(started, ev.JourneyStarted)
    assert started.destination_stop_id == "S4"
    completed = stored[1]
    assert isinstance(completed, ev.JourneyCompleted)
    assert completed.missed is False


async def test_service_alert_emits_event(resources: AppResources) -> None:
    async with resources.session_factory() as session:
        async with session.begin():
            await resources.commuter.service_alerts.create(
                session, title="Red line delay", description="10 min",
                severity="warning", route_id="R1",
            )
    stored = await _read_events(resources.redis)
    alert_events = [e for e in stored if isinstance(e, ev.ServiceAlertCreated)]
    assert len(alert_events) == 1
    assert alert_events[0].route_id == "R1"


async def test_realtime_engine_emits_vehicle_events(resources: AppResources) -> None:
    from metropulse.application.realtime_engine import RealtimeEngine
    from test_realtime_engine import StubFeed

    feed = StubFeed()
    feed.queue([make_vehicle("v1"), make_vehicle("v2", longitude=77.02, trip_id="T2")])
    feed.queue([make_vehicle("v1")])  # v2 disappears
    engine = RealtimeEngine(
        feed,
        resources.vehicle_store,
        resources.session_factory,
        resources.train_service,
        event_publisher=resources.event_publisher,
    )

    await engine.poll_once()
    await engine.poll_once()

    stored = await _read_events(resources.redis)
    updated = [e for e in stored if isinstance(e, ev.VehicleUpdated)]
    removed = [e for e in stored if isinstance(e, ev.VehicleRemoved)]
    assert {(e.vehicle_id, e.change) for e in updated} == {("v1", "added"), ("v2", "added")}
    assert [e.vehicle_id for e in removed] == ["v2"]
