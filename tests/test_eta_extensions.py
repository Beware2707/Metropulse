"""Tests for Sprint-2 ETA additions: delay, dwell estimation, Redis caching."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import fakeredis.aioredis
import pytest

from factories import make_vehicle
from metropulse.application.eta_engine import EtaEngine, EtaParameters
from metropulse.application.eta_service import CachedEtaService
from metropulse.application.route_resolver import RouteResolver
from metropulse.domain.entities import StationEta, StopOnTrip, TripContext, VehicleEta
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.repositories import VehicleHistoryRepository
from metropulse.infrastructure.redis.eta_cache import RedisEtaCache

IST = ZoneInfo("Asia/Kolkata")
PARAMS = EtaParameters(dwell_time_seconds=25.0, timezone="Asia/Kolkata")


def _stop(arrival_seconds: int) -> StopOnTrip:
    return StopOnTrip(
        stop_id="S3", stop_name="Charlie", sequence=3, latitude=28.6, longitude=77.02,
        arrival_seconds=arrival_seconds, departure_seconds=arrival_seconds + 30,
        distance_along_shape_m=2000.0,
    )


def _eta_at(eta_time: datetime) -> StationEta:
    return StationEta(
        stop_id="S3", stop_name="Charlie", sequence=3,
        distance_remaining_m=500.0, eta_seconds=50.0, eta_time=eta_time,
    )


def test_arrival_delay_positive_when_late(loaded_session_factory: SessionFactory) -> None:
    engine = EtaEngine(loaded_session_factory, PARAMS)
    # Scheduled 08:06:00 IST, predicted 08:10:00 IST -> 4 minutes late.
    predicted = datetime(2026, 7, 6, 8, 10, 0, tzinfo=IST)
    delay = engine._arrival_delay(_eta_at(predicted), _stop(8 * 3600 + 6 * 60))
    assert delay == pytest.approx(240.0)


def test_arrival_delay_negative_when_early(loaded_session_factory: SessionFactory) -> None:
    engine = EtaEngine(loaded_session_factory, PARAMS)
    predicted = datetime(2026, 7, 6, 8, 4, 0, tzinfo=IST)
    delay = engine._arrival_delay(_eta_at(predicted), _stop(8 * 3600 + 6 * 60))
    assert delay == pytest.approx(-120.0)


def test_arrival_delay_handles_past_midnight_service_day(
    loaded_session_factory: SessionFactory,
) -> None:
    engine = EtaEngine(loaded_session_factory, PARAMS)
    # Scheduled 25:10 (01:10 next civil day); predicted 01:15 -> 5 min late,
    # anchored to *yesterday's* service date.
    predicted = datetime(2026, 7, 7, 1, 15, 0, tzinfo=IST)
    delay = engine._arrival_delay(_eta_at(predicted), _stop(25 * 3600 + 10 * 60))
    assert delay == pytest.approx(300.0)


def test_arrival_delay_implausible_returns_none(
    loaded_session_factory: SessionFactory,
) -> None:
    engine = EtaEngine(loaded_session_factory, PARAMS)
    predicted = datetime(2026, 7, 6, 20, 6, 0, tzinfo=IST)  # 12h off schedule
    delay = engine._arrival_delay(_eta_at(predicted), _stop(8 * 3600 + 6 * 60))
    assert delay is None


async def test_dwell_estimated_from_stationary_bouts(
    loaded_session_factory: SessionFactory,
) -> None:
    now = datetime.now(UTC)
    # Moving -> stationary for 40s (3 samples) -> moving again.
    lons = [77.010, 77.012, 77.012, 77.012, 77.014]
    offsets = [-70, -50, -30, -10, 0]
    async with loaded_session_factory() as session:
        async with session.begin():
            repo = VehicleHistoryRepository(session)
            for lon, offset in zip(lons, offsets):
                ts = now + timedelta(seconds=offset)
                await repo.add_many(
                    [make_vehicle("v1", longitude=lon, timestamp=ts)], recorded_at=ts
                )

    engine = EtaEngine(loaded_session_factory, PARAMS)
    dwell = await engine._estimate_dwell("v1")
    assert dwell == pytest.approx(40.0, abs=1.0)


async def test_dwell_falls_back_to_default_without_history(
    loaded_session_factory: SessionFactory, resolver: RouteResolver
) -> None:
    engine = EtaEngine(loaded_session_factory, PARAMS)
    context = await resolver.resolve_trip("T1")
    assert context is not None
    eta = await engine.compute(make_vehicle(longitude=77.015, speed_mps=10.0), context)
    assert eta is not None
    assert eta.dwell_seconds_used == pytest.approx(25.0)
    assert eta.next_station is not None
    assert eta.next_station == eta.stations[0]
    assert eta.next_station.stop_id == "S3"


class CountingEngine:
    """EtaEngine stand-in that counts compute() invocations."""

    def __init__(self, result: VehicleEta | None) -> None:
        self.result = result
        self.calls = 0

    async def compute(self, vehicle: object, context: object) -> VehicleEta | None:
        self.calls += 1
        return self.result


def _sample_eta(vehicle_id: str = "v1") -> VehicleEta:
    now = datetime.now(UTC)
    station = StationEta(
        stop_id="S3", stop_name="Charlie", sequence=3,
        distance_remaining_m=500.0, eta_seconds=50.0,
        eta_time=now + timedelta(seconds=50),
    )
    return VehicleEta(
        vehicle_id=vehicle_id, trip_id="T1", computed_at=now,
        speed_mps_used=10.0, speed_source="reported", confidence="high",
        stations=(station,), next_station=station,
        delay_seconds=12.5, dwell_seconds_used=25.0,
    )


async def test_cached_eta_service_serves_from_cache(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    engine = CountingEngine(_sample_eta())
    service = CachedEtaService(engine, RedisEtaCache(fake_redis))  # type: ignore[arg-type]
    vehicle = make_vehicle("v1")

    first = await service.compute(vehicle, _dummy_context())
    second = await service.compute(vehicle, _dummy_context())

    assert engine.calls == 1  # second call was a cache hit
    assert first is not None and second is not None
    assert second.delay_seconds == pytest.approx(12.5)
    assert second.next_station is not None
    assert second.next_station.stop_id == "S3"


async def test_cached_eta_invalidated_when_vehicle_moves(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    engine = CountingEngine(_sample_eta())
    service = CachedEtaService(engine, RedisEtaCache(fake_redis))  # type: ignore[arg-type]
    vehicle = make_vehicle("v1")
    await service.compute(vehicle, _dummy_context())

    moved = make_vehicle("v1", timestamp=vehicle.timestamp + timedelta(seconds=5))
    await service.compute(moved, _dummy_context())

    assert engine.calls == 2  # new feed sample -> recompute


async def test_eta_round_trips_through_redis(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    cache = RedisEtaCache(fake_redis)
    eta = _sample_eta()
    ts = datetime.now(UTC)
    await cache.set("v1", ts, eta)
    loaded = await cache.get("v1", ts)
    assert loaded == eta
    # Wrong timestamp -> miss.
    assert await cache.get("v1", ts + timedelta(seconds=1)) is None


class BrokenCache:
    """Cache whose reads and writes always fail."""

    async def get(self, vehicle_id: str, vehicle_timestamp: datetime) -> VehicleEta | None:
        raise ConnectionError("redis down")

    async def set(
        self, vehicle_id: str, vehicle_timestamp: datetime, eta: VehicleEta
    ) -> None:
        raise ConnectionError("redis down")


async def test_cache_failure_degrades_to_computation() -> None:
    engine = CountingEngine(_sample_eta())
    service = CachedEtaService(engine, BrokenCache())  # type: ignore[arg-type]
    result = await service.compute(make_vehicle("v1"), _dummy_context())
    assert result is not None
    assert engine.calls == 1


def _dummy_context() -> TripContext:
    return TripContext(
        trip_id="T1", route_id="R1", route_short_name="RED", route_long_name="Red Line",
        route_color="EE1C25", headsign="Towards Delta", direction_id=0,
        shape_id=None, stops=(), geometry=None,
    )
