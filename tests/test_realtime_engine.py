"""Tests for the realtime polling engine: diffing, staleness, persistence."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

from factories import build_feed_payload, make_vehicle
from metropulse.application.events import FEED_UPDATED, EventBus
from metropulse.application.realtime_engine import PollResult, RealtimeEngine
from metropulse.application.route_resolver import RouteResolver
from metropulse.application.train_service import TrainService
from metropulse.domain.entities import VehiclePosition
from metropulse.domain.exceptions import FeedFetchError
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.repositories import VehicleHistoryRepository
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore


class StubFeed:
    """FeedSource stub returning queued payloads (or raising queued errors)."""

    def __init__(self) -> None:
        self.payloads: list[bytes | Exception] = []

    def queue(self, vehicles: list[VehiclePosition]) -> None:
        self.payloads.append(build_feed_payload(vehicles))

    def queue_error(self, error: Exception) -> None:
        self.payloads.append(error)

    async def fetch_vehicle_positions(self) -> bytes:
        item = self.payloads.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _engine(
    feed: StubFeed,
    store: RedisVehicleStore,
    session_factory: SessionFactory,
    resolver: RouteResolver,
    stale_after_seconds: float = 90.0,
) -> RealtimeEngine:
    train_service = TrainService(store, resolver, stale_after_seconds)
    return RealtimeEngine(
        feed, store, session_factory, train_service, stale_after_seconds=stale_after_seconds
    )


async def test_first_poll_stores_and_persists_everything(
    store: RedisVehicleStore,
    loaded_session_factory: SessionFactory,
    resolver: RouteResolver,
) -> None:
    feed = StubFeed()
    feed.queue([make_vehicle("v1"), make_vehicle("v2", longitude=77.02, trip_id="T2")])
    engine = _engine(feed, store, loaded_session_factory, resolver)

    result = await engine.poll_once()

    assert result.total == 2
    assert result.added == ("v1", "v2")
    assert result.moved == ()
    assert result.removed == ()
    snapshot = await store.get_all()
    assert set(snapshot) == {"v1", "v2"}
    # Resolution results are cached in Redis for API replicas.
    cached = await store.get_all_train_states()
    assert set(cached) == {"v1", "v2"}
    assert cached["v1"].route_long_name == "Red Line"
    async with loaded_session_factory() as session:
        rows = await VehicleHistoryRepository(session).recent_for_vehicle("v1")
        assert len(rows) == 1


async def test_second_poll_reports_only_changes(
    store: RedisVehicleStore,
    loaded_session_factory: SessionFactory,
    resolver: RouteResolver,
) -> None:
    ts = datetime.now(UTC)
    v1 = make_vehicle("v1", timestamp=ts)
    v2 = make_vehicle("v2", longitude=77.02, trip_id="T2", timestamp=ts)
    feed = StubFeed()
    feed.queue([v1, v2])
    # v1 unchanged, v2 moved, v3 appears.
    v2_moved = make_vehicle("v2", longitude=77.025, trip_id="T2", timestamp=ts)
    feed.queue([v1, v2_moved, make_vehicle("v3", timestamp=ts)])
    engine = _engine(feed, store, loaded_session_factory, resolver)

    await engine.poll_once()
    result = await engine.poll_once()

    assert result.added == ("v3",)
    assert result.moved == ("v2",)
    assert result.changed == ("v3", "v2")
    assert result.removed == ()
    assert result.sequence == 2


async def test_removed_vehicles_are_detected_and_evicted(
    store: RedisVehicleStore,
    loaded_session_factory: SessionFactory,
    resolver: RouteResolver,
) -> None:
    feed = StubFeed()
    feed.queue([make_vehicle("v1"), make_vehicle("v2", longitude=77.02)])
    feed.queue([make_vehicle("v1")])
    engine = _engine(feed, store, loaded_session_factory, resolver)

    await engine.poll_once()
    result = await engine.poll_once()

    assert result.removed == ("v2",)
    snapshot = await store.get_all()
    assert set(snapshot) == {"v1"}
    # The cached resolution is evicted alongside the vehicle.
    cached = await store.get_all_train_states()
    assert set(cached) == {"v1"}


async def test_stale_vehicles_are_flagged(
    store: RedisVehicleStore,
    loaded_session_factory: SessionFactory,
    resolver: RouteResolver,
) -> None:
    old = datetime.now(UTC) - timedelta(minutes=10)
    feed = StubFeed()
    feed.queue([make_vehicle("v1", timestamp=old), make_vehicle("v2")])
    engine = _engine(feed, store, loaded_session_factory, resolver)

    result = await engine.poll_once()

    assert result.stale == ("v1",)


async def test_diff_message_is_published_with_enrichment(
    store: RedisVehicleStore,
    loaded_session_factory: SessionFactory,
    resolver: RouteResolver,
) -> None:
    received: list[str] = []

    async def collect() -> None:
        async for message in store.subscribe_diffs():
            received.append(message)
            return

    collector = asyncio.create_task(collect())
    await asyncio.sleep(0.05)  # let the subscription register

    feed = StubFeed()
    feed.queue([make_vehicle("v1", longitude=77.015)])
    engine = _engine(feed, store, loaded_session_factory, resolver)
    await engine.poll_once()
    await asyncio.wait_for(collector, timeout=2)

    message = json.loads(received[0])
    assert message["type"] == "update"
    assert message["seq"] == 1
    assert message["removed"] == []
    assert message["moved"] == []
    train = message["added"][0]
    assert train["vehicle"]["vehicle_id"] == "v1"
    assert train["resolved"] is True
    assert train["route_long_name"] == "Red Line"
    assert train["current_station"]["stop_id"] == "S2"
    assert train["next_station"]["stop_id"] == "S3"
    assert train["destination"]["stop_id"] == "S4"
    assert [s["stop_id"] for s in train["remaining_stations"]] == ["S3", "S4"]


async def test_poll_publishes_feed_updated_event(
    store: RedisVehicleStore,
    loaded_session_factory: SessionFactory,
    resolver: RouteResolver,
) -> None:
    received: list[PollResult] = []
    bus = EventBus()

    async def handler(result: PollResult) -> None:
        received.append(result)

    bus.subscribe(FEED_UPDATED, handler)

    feed = StubFeed()
    feed.queue([make_vehicle("v1")])
    train_service = TrainService(store, resolver, 90.0)
    engine = RealtimeEngine(
        feed, store, loaded_session_factory, train_service, event_bus=bus
    )
    result = await engine.poll_once()

    assert received == [result]
    assert received[0].added == ("v1",)


async def test_poll_safe_swallows_and_counts_failures(
    store: RedisVehicleStore,
    loaded_session_factory: SessionFactory,
    resolver: RouteResolver,
) -> None:
    feed = StubFeed()
    feed.queue_error(FeedFetchError("network down"))
    feed.queue([make_vehicle("v1")])
    engine = _engine(feed, store, loaded_session_factory, resolver)

    assert await engine.poll_safe() is None
    assert engine.stats.failures == 1
    assert engine.stats.consecutive_failures == 1
    assert engine.stats.last_error == "network down"

    result = await engine.poll_safe()
    assert result is not None
    assert engine.stats.consecutive_failures == 0


async def test_poll_safe_survives_unexpected_errors(
    store: RedisVehicleStore,
    loaded_session_factory: SessionFactory,
    resolver: RouteResolver,
) -> None:
    feed = StubFeed()
    feed.queue_error(RuntimeError("something entirely unexpected"))
    engine = _engine(feed, store, loaded_session_factory, resolver)

    assert await engine.poll_safe() is None
    assert engine.stats.failures == 1
