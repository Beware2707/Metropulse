"""FastAPI dependencies resolving shared resources from app state."""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.eta_engine import EtaEngine
from metropulse.application.route_resolver import RouteResolver
from metropulse.application.train_service import TrainService
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session."""
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_vehicle_store(request: Request) -> RedisVehicleStore:
    """The shared Redis vehicle store."""
    store: RedisVehicleStore = request.app.state.vehicle_store
    return store


def get_resolver(request: Request) -> RouteResolver:
    """The shared route resolver (with its trip-context cache)."""
    resolver: RouteResolver = request.app.state.resolver
    return resolver


def get_train_service(request: Request) -> TrainService:
    """The shared train assembly service."""
    service: TrainService = request.app.state.train_service
    return service


def get_eta_engine(request: Request) -> EtaEngine:
    """The shared ETA engine."""
    engine: EtaEngine = request.app.state.eta_engine
    return engine
