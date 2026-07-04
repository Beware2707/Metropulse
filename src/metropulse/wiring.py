"""Composition root: builds the object graph from Settings.

Both entry points (API app and realtime worker) assemble their dependencies
here so tests can substitute an entire pre-built :class:`AppResources` with
in-memory fakes without monkeypatching.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from metropulse.application.eta_engine import EtaEngine, EtaParameters
from metropulse.application.live_hub import ConnectionManager, LiveHub, ReplayBuffer
from metropulse.application.route_resolver import IdMapper, MappingRule, RouteResolver
from metropulse.application.train_service import TrainService
from metropulse.config import Settings
from metropulse.infrastructure.db.base import (
    SessionFactory,
    create_engine,
    create_session_factory,
)
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore


@dataclass
class AppResources:
    """Everything a MetroPulse process needs, built once at startup."""

    settings: Settings
    engine: AsyncEngine | None
    session_factory: SessionFactory
    redis: Redis
    vehicle_store: RedisVehicleStore
    resolver: RouteResolver
    train_service: TrainService
    eta_engine: EtaEngine
    live_hub: LiveHub
    owns_connections: bool = True

    async def close(self) -> None:
        """Dispose owned connections (no-op for injected test resources)."""
        if not self.owns_connections:
            return
        await self.redis.aclose()
        if self.engine is not None:
            await self.engine.dispose()


def build_id_mapper(settings: Settings) -> IdMapper:
    """Construct the ID mapper from configured rules and the optional map file."""
    trip_map, route_map = settings.load_static_id_maps()
    rules = [
        MappingRule(field=rule.field, pattern=rule.pattern, replacement=rule.replacement)
        for rule in settings.id_mapping_rules
    ]
    return IdMapper(rules=rules, trip_id_map=trip_map, route_id_map=route_map)


def build_resources(settings: Settings) -> AppResources:
    """Build the full production object graph from settings."""
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    vehicle_store = RedisVehicleStore(redis)
    resolver = RouteResolver(
        session_factory,
        build_id_mapper(settings),
        station_radius_m=settings.station_radius_m,
    )
    train_service = TrainService(vehicle_store, resolver, settings.stale_after_seconds)
    eta_engine = EtaEngine(
        session_factory,
        EtaParameters(
            default_speed_mps=settings.default_speed_mps,
            min_speed_mps=settings.min_speed_mps,
            max_speed_mps=settings.max_speed_mps,
            dwell_time_seconds=settings.dwell_time_seconds,
            station_radius_m=settings.station_radius_m,
        ),
    )
    live_hub = LiveHub(ConnectionManager(), ReplayBuffer(settings.ws_replay_buffer_size))
    return AppResources(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        redis=redis,
        vehicle_store=vehicle_store,
        resolver=resolver,
        train_service=train_service,
        eta_engine=eta_engine,
        live_hub=live_hub,
    )


def build_http_client(settings: Settings) -> httpx.AsyncClient:
    """HTTP client for the realtime feed with sane timeouts and pooling."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        headers={"User-Agent": "MetroPulse/1.0"},
    )
