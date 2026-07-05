"""Tests for the feed-update event consumers (ETA warming, analytics)."""

from __future__ import annotations

from typing import Any

import fakeredis.aioredis
from sqlalchemy import select

from factories import make_vehicle
from metropulse.application.consumers import EtaWarmer, FeedAnalyticsRecorder
from metropulse.application.eta_engine import EtaEngine, EtaParameters
from metropulse.application.eta_service import CachedEtaService
from metropulse.application.route_resolver import RouteResolver
from metropulse.application.train_service import TrainService
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import AnalyticsEvent
from metropulse.infrastructure.redis.eta_cache import RedisEtaCache
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore


async def _update_event(
    store: RedisVehicleStore, resolver: RouteResolver
) -> tuple[dict[str, Any], Any]:
    vehicle = make_vehicle("v1", longitude=77.015, speed_mps=10.0)
    state = await TrainService(store, resolver, 90.0).assemble(vehicle)
    event = {
        "type": "update",
        "seq": 3,
        "ts": utcnow().isoformat(),
        "added": [state.to_dict()],
        "moved": [],
        "removed": [],
        "stale": [],
    }
    return event, vehicle


async def test_eta_warmer_populates_cache(
    store: RedisVehicleStore,
    resolver: RouteResolver,
    loaded_session_factory: SessionFactory,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    cache = RedisEtaCache(fake_redis)
    eta_service = CachedEtaService(EtaEngine(loaded_session_factory, EtaParameters()), cache)
    warmer = EtaWarmer(resolver, eta_service)
    event, vehicle = await _update_event(store, resolver)

    await warmer.handle(event)

    cached = await cache.get(vehicle.vehicle_id, vehicle.timestamp)
    assert cached is not None
    assert [s.stop_id for s in cached.stations] == ["S3", "S4"]


async def test_eta_warmer_ignores_non_update_and_tripless(
    store: RedisVehicleStore,
    resolver: RouteResolver,
    loaded_session_factory: SessionFactory,
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    cache = RedisEtaCache(fake_redis)
    eta_service = CachedEtaService(EtaEngine(loaded_session_factory, EtaParameters()), cache)
    warmer = EtaWarmer(resolver, eta_service)

    await warmer.handle({"type": "alert", "alert": {}})

    tripless = make_vehicle("v2", trip_id=None)
    state = await TrainService(store, resolver, 90.0).assemble(tripless)
    await warmer.handle({"type": "update", "added": [state.to_dict()], "moved": []})
    assert await cache.get("v2", tripless.timestamp) is None


async def test_analytics_recorder_persists_feed_telemetry(
    store: RedisVehicleStore,
    resolver: RouteResolver,
    loaded_session_factory: SessionFactory,
) -> None:
    recorder = FeedAnalyticsRecorder(loaded_session_factory)
    event, _ = await _update_event(store, resolver)
    event["removed"] = ["gone-1"]

    await recorder.handle(event)
    await recorder.handle({"type": "alert"})  # ignored

    async with loaded_session_factory() as session:
        rows = (await session.execute(select(AnalyticsEvent))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.event_type == "feed_update"
    assert row.user_id is None
    assert row.payload is not None
    assert row.payload["seq"] == 3
    assert row.payload["added"] == 1
    assert row.payload["removed"] == 1
