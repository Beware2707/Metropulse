"""Shared fixtures: SQLite database, loaded GTFS data, fake Redis."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import fakeredis.aioredis
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from gtfs_fixture import write_gtfs_zip
from metropulse.application.route_resolver import IdMapper, RouteResolver
from metropulse.application.static_loader import GtfsStaticLoader
from metropulse.config import Settings
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.models import Base
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Isolated settings that never read a developer's .env file."""
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'settings.db').as_posix()}",
        ws_heartbeat_seconds=60.0,
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
