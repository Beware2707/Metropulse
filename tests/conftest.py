"""Shared fixtures: SQLite database, loaded GTFS data, fake Redis, API client."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import fakeredis.aioredis
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from gtfs_fixture import write_gtfs_zip
from metropulse.application.eta_engine import EtaEngine, EtaParameters
from metropulse.application.eta_service import CachedEtaService
from metropulse.application.live_hub import ConnectionManager, LiveHub, ReplayBuffer
from metropulse.application.route_resolver import IdMapper, RouteResolver
from metropulse.application.static_loader import GtfsStaticLoader
from metropulse.application.train_service import TrainService
from metropulse.config import Settings
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.models import Base
from metropulse.infrastructure.redis.eta_cache import RedisEtaCache
from metropulse.infrastructure.redis.event_publisher import RedisDomainEventPublisher
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore
from metropulse.main import create_app
from metropulse.wiring import AppResources, build_commuter_services

ADMIN_KEY = "test-admin-key"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Isolated settings that never read a developer's .env file."""
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'settings.db').as_posix()}",
        ws_heartbeat_seconds=60.0,
        admin_api_key=ADMIN_KEY,
    )


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    """File-backed SQLite URL (in-memory SQLite breaks across connections)."""
    return f"sqlite+aiosqlite:///{(tmp_path / 'metropulse.db').as_posix()}"


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    """Async engine with the full schema created."""
    engine = create_async_engine(db_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> SessionFactory:
    """Session factory over the test engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def gtfs_zip(tmp_path: Path) -> Path:
    """The standard fixture GTFS static ZIP."""
    return write_gtfs_zip(tmp_path / "gtfs.zip")


@pytest.fixture
async def loaded_session_factory(
    session_factory: SessionFactory, gtfs_zip: Path
) -> SessionFactory:
    """Session factory with the fixture dataset already loaded."""
    await GtfsStaticLoader(session_factory).load(gtfs_zip)
    return session_factory


@pytest.fixture
async def fake_redis() -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    """In-process Redis replacement."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()


@pytest.fixture
def store(fake_redis: fakeredis.aioredis.FakeRedis) -> RedisVehicleStore:
    """Vehicle store over fake Redis."""
    return RedisVehicleStore(fake_redis)


@pytest.fixture
def resolver(loaded_session_factory: SessionFactory) -> RouteResolver:
    """Route resolver over the loaded fixture dataset."""
    return RouteResolver(loaded_session_factory, IdMapper(), station_radius_m=75.0)


@pytest.fixture
def resources(
    loaded_session_factory: SessionFactory,
    fake_redis: fakeredis.aioredis.FakeRedis,
    settings: Settings,
) -> AppResources:
    """A full object graph over SQLite + fake Redis."""
    store = RedisVehicleStore(fake_redis)
    resolver = RouteResolver(loaded_session_factory, IdMapper(), station_radius_m=75.0)
    eta_engine = EtaEngine(loaded_session_factory, EtaParameters())
    event_publisher = RedisDomainEventPublisher(fake_redis)
    return AppResources(
        settings=settings,
        engine=None,
        session_factory=loaded_session_factory,
        redis=fake_redis,
        vehicle_store=store,
        resolver=resolver,
        train_service=TrainService(store, resolver, settings.stale_after_seconds),
        eta_engine=eta_engine,
        eta_service=CachedEtaService(eta_engine, RedisEtaCache(fake_redis)),
        live_hub=LiveHub(ConnectionManager(), ReplayBuffer(64)),
        commuter=build_commuter_services(
            settings, loaded_session_factory, fake_redis, store, event_publisher
        ),
        event_publisher=event_publisher,
        owns_connections=False,
    )


@pytest.fixture
async def api_client(
    resources: AppResources, settings: Settings
) -> AsyncIterator[httpx.AsyncClient]:
    """In-process API client with the real lifespan running."""
    app = create_app(settings, resources)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def auth_headers(api_client: httpx.AsyncClient) -> dict[str, str]:
    """Bearer-token headers for a freshly registered test user."""
    response = await api_client.post(
        "/api/v1/users", json={"device_id": "test-device", "platform": "android"}
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """Headers for admin endpoints."""
    return {"X-Admin-Key": ADMIN_KEY}
