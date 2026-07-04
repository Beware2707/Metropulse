"""Async engine and session factory construction."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SessionFactory = async_sessionmaker[AsyncSession]


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Create the application's async engine with production pool settings."""
    kwargs: dict[str, object] = {"echo": echo, "pool_pre_ping": True}
    if not database_url.startswith("sqlite"):
        # SQLite (used in tests) rejects pool sizing arguments.
        kwargs.update({"pool_size": 10, "max_overflow": 20})
    return create_async_engine(database_url, **kwargs)  # type: ignore[arg-type]


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    """Create the async session factory bound to an engine."""
    return async_sessionmaker(engine, expire_on_commit=False)
