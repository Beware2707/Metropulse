"""FastAPI dependencies: shared resources, bearer-token auth, admin guard."""

from __future__ import annotations

import secrets
from typing import AsyncIterator

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.application.eta_service import CachedEtaService
from metropulse.application.route_resolver import RouteResolver
from metropulse.application.train_service import TrainService
from metropulse.infrastructure.db.commuter_models import User
from metropulse.infrastructure.redis.vehicle_store import RedisVehicleStore
from metropulse.wiring import CommuterServices


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


def get_eta_service(request: Request) -> CachedEtaService:
    """The Redis-cached ETA service (API-facing interface)."""
    service: CachedEtaService = request.app.state.eta_service
    return service


def get_commuter(request: Request) -> CommuterServices:
    """The commuter service bundle."""
    services: CommuterServices = request.app.state.commuter
    return services


async def get_current_user(
    request: Request, authorization: str | None = Header(default=None)
) -> User:
    """Authenticate the bearer token and return the user (401 otherwise)."""
    user = await _resolve_user(request, authorization)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_optional_user(
    request: Request, authorization: str | None = Header(default=None)
) -> User | None:
    """Like get_current_user but anonymous access is allowed."""
    return await _resolve_user(request, authorization)


async def _resolve_user(request: Request, authorization: str | None) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    services: CommuterServices = request.app.state.commuter
    factory = request.app.state.session_factory
    async with factory() as session:
        async with session.begin():
            return await services.users.authenticate(session, token)


def require_admin(
    request: Request, x_admin_key: str | None = Header(default=None)
) -> None:
    """Guard admin endpoints with the configured API key (403 otherwise).

    An empty configured key disables admin endpoints entirely.
    """
    configured: str = request.app.state.settings.admin_api_key
    if not configured or x_admin_key is None or not secrets.compare_digest(
        configured, x_admin_key
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin access denied"
        )
