"""Tests for the token-bucket rate-limit middleware."""

from __future__ import annotations

from typing import AsyncIterator

import httpx
import pytest

from metropulse.config import Settings
from metropulse.main import create_app
from metropulse.wiring import AppResources


@pytest.fixture
async def limited_client(resources: AppResources) -> AsyncIterator[httpx.AsyncClient]:
    """A client against an app allowing a burst of 2 requests."""
    settings = Settings(
        _env_file=None,
        rate_limit_per_minute=60,
        rate_limit_burst=2,
        ws_heartbeat_seconds=60.0,
    )
    app = create_app(settings, resources)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_burst_exhaustion_returns_429(limited_client: httpx.AsyncClient) -> None:
    first = await limited_client.get("/api/v1/routes")
    second = await limited_client.get("/api/v1/routes")
    third = await limited_client.get("/api/v1/routes")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json() == {"detail": "rate limit exceeded"}
    assert int(third.headers["retry-after"]) >= 1


async def test_ops_endpoints_are_exempt(limited_client: httpx.AsyncClient) -> None:
    for _ in range(5):
        response = await limited_client.get("/health")
        assert response.status_code == 200
    metrics = await limited_client.get("/metrics")
    assert metrics.status_code == 200


async def test_rate_limiting_can_be_disabled(resources: AppResources) -> None:
    settings = Settings(_env_file=None, rate_limit_per_minute=0, ws_heartbeat_seconds=60.0)
    app = create_app(settings, resources)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(10):
                assert (await client.get("/api/v1/routes")).status_code == 200
