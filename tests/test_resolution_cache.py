"""Tests for Redis-cached route resolution (worker writes, API reads)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

from factories import make_vehicle
from metropulse.application.route_resolver import RouteResolver
from metropulse.application.train_service import TrainService
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore


async def _cache_marker_state(
    store: RedisVehicleStore,
    resolver: RouteResolver,
    vehicle_id: str,
) -> None:
    """Cache a real resolved state, watermarked so cache hits are detectable."""
    service = TrainService(store, resolver, 90.0)
    vehicle = (await store.get_all())[vehicle_id]
    state = await service.assemble(vehicle)
    marked = dataclasses.replace(state, route_long_name="FROM-CACHE")
    await store.cache_train_states({vehicle_id: marked.to_dict()})


async def test_train_state_round_trips_through_redis(
    store: RedisVehicleStore, resolver: RouteResolver
) -> None:
    vehicle = make_vehicle("v1", longitude=77.015)
    service = TrainService(store, resolver, 90.0)
    state = await service.assemble(vehicle)

    await store.cache_train_states({"v1": state.to_dict()})
    loaded = await store.get_train_state("v1")

    assert loaded is not None
    assert loaded.route_long_name == "Red Line"
    assert loaded.current_station == state.current_station
    assert [s.stop_id for s in loaded.remaining_stations] == ["S3", "S4"]
    assert loaded == state


async def test_fresh_cache_is_served_without_recomputing(
    store: RedisVehicleStore,
    resolver: RouteResolver,
) -> None:
    vehicle = make_vehicle("v1", longitude=77.015)
    await store.apply({"v1": vehicle}, [])
    await _cache_marker_state(store, resolver, "v1")

    service = TrainService(store, resolver, 90.0)
    single = await service.get_train("v1")
    assert single is not None
    assert single.route_long_name == "FROM-CACHE"

    listing = await service.list_trains()
    assert listing[0].route_long_name == "FROM-CACHE"


async def test_stale_cache_triggers_recomputation(
    store: RedisVehicleStore,
    resolver: RouteResolver,
) -> None:
    vehicle = make_vehicle("v1", longitude=77.015)
    await store.apply({"v1": vehicle}, [])
    await _cache_marker_state(store, resolver, "v1")

    # The vehicle sends a fresh position: the cached state no longer matches.
    newer = make_vehicle(
        "v1", longitude=77.016, timestamp=vehicle.timestamp + timedelta(seconds=5)
    )
    await store.apply({"v1": newer}, [])

    service = TrainService(store, resolver, 90.0)
    state = await service.get_train("v1")
    assert state is not None
    assert state.route_long_name == "Red Line"  # recomputed, marker gone


async def test_cached_staleness_is_rederived_at_read_time(
    store: RedisVehicleStore,
    resolver: RouteResolver,
) -> None:
    # Cached 'fresh' state for a vehicle whose timestamp is now ancient.
    old = datetime.now(UTC) - timedelta(minutes=30)
    vehicle = make_vehicle("v1", timestamp=old)
    await store.apply({"v1": vehicle}, [])
    service = TrainService(store, resolver, stale_after_seconds=90.0)
    state = await service.assemble(vehicle)
    cached_dict = state.to_dict()
    cached_dict["is_stale"] = False  # simulate a state cached while fresh
    await store.cache_train_states({"v1": cached_dict})

    result = await service.get_train("v1")
    assert result is not None
    assert result.is_stale is True
