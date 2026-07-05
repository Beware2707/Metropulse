"""Tests for the realtime feed HTTP client (retry behaviour)."""

from __future__ import annotations

import httpx
import pytest

from metropulse.domain.exceptions import FeedFetchError
from metropulse.infrastructure.gtfs_rt.client import GtfsRtClient

FEED_URL = "https://example.test/VehiclePositions.pb"


def _client_with(handler: httpx.MockTransport, max_attempts: int = 3) -> GtfsRtClient:
    http = httpx.AsyncClient(transport=handler)
    return GtfsRtClient(
        http, FEED_URL, "secret-key", max_attempts=max_attempts, backoff_base_seconds=0.01
    )


async def test_fetch_success_sends_api_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"payload")

    client = _client_with(httpx.MockTransport(handler))
    assert await client.fetch_vehicle_positions() == b"payload"
    assert seen[0].url.params["key"] == "secret-key"


async def test_fetch_retries_then_succeeds() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(500)
        return httpx.Response(200, content=b"ok")

    client = _client_with(httpx.MockTransport(handler))
    assert await client.fetch_vehicle_positions() == b"ok"
    assert calls["count"] == 3


async def test_fetch_raises_after_exhausting_attempts() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503)

    client = _client_with(httpx.MockTransport(handler), max_attempts=3)
    with pytest.raises(FeedFetchError, match="HTTP 503"):
        await client.fetch_vehicle_positions()
    assert calls["count"] == 3


async def test_fetch_retries_on_transport_error() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, content=b"ok")

    client = _client_with(httpx.MockTransport(handler))
    assert await client.fetch_vehicle_positions() == b"ok"
    assert calls["count"] == 2


async def test_empty_body_is_a_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    client = _client_with(httpx.MockTransport(handler), max_attempts=1)
    with pytest.raises(FeedFetchError, match="empty body"):
        await client.fetch_vehicle_positions()


def _failing_client(max_attempts: int = 1, threshold: int = 3) -> GtfsRtClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GtfsRtClient(
        http, FEED_URL, "k",
        max_attempts=max_attempts,
        backoff_base_seconds=0.01,
        circuit_failure_threshold=threshold,
        circuit_reset_seconds=60.0,
    )


async def test_circuit_opens_after_consecutive_failed_cycles() -> None:
    client = _failing_client(threshold=3)
    for _ in range(3):
        with pytest.raises(FeedFetchError):
            await client.fetch_vehicle_positions()
    assert client.circuit_open is True
    # While open, the client fails fast without touching the network.
    with pytest.raises(FeedFetchError, match="circuit open"):
        await client.fetch_vehicle_positions()


async def test_success_resets_the_circuit_counter() -> None:
    # Scripted upstream: two failures, one success, then two more failures.
    script = [500, 500, 200, 500, 500]
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        status = script[min(calls["count"], len(script) - 1)]
        calls["count"] += 1
        if status == 200:
            return httpx.Response(200, content=b"ok")
        return httpx.Response(status)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = GtfsRtClient(
        http, FEED_URL, "k",
        max_attempts=1, backoff_base_seconds=0.01,
        circuit_failure_threshold=3, circuit_reset_seconds=60.0,
    )
    for _ in range(2):
        with pytest.raises(FeedFetchError):
            await client.fetch_vehicle_positions()
    assert await client.fetch_vehicle_positions() == b"ok"
    assert client.circuit_open is False
    # The failure streak was reset: two more failures do not open the circuit.
    for _ in range(2):
        with pytest.raises(FeedFetchError):
            await client.fetch_vehicle_positions()
    assert client.circuit_open is False
