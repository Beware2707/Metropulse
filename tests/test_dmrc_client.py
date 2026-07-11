"""Tests for the DMRC static GTFS feed HTTP client (CSRF handshake, retries)."""

from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest

from metropulse.domain.exceptions import FeedFetchError
from metropulse.infrastructure.gtfs_static.dmrc_client import DmrcStaticFeedClient

FEED_URL = "https://example.test/data/staticDMRC/"


def _client_with(handler: httpx.MockTransport, max_attempts: int = 3) -> DmrcStaticFeedClient:
    http = httpx.AsyncClient(transport=handler)
    return DmrcStaticFeedClient(
        http, FEED_URL, max_attempts=max_attempts, backoff_base_seconds=0.01
    )


async def test_fetch_sends_matching_csrf_cookie_and_form_field() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            content=b"PK\x03\x04zipbytes",
            headers={"ETag": '"abc123"', "Last-Modified": "Wed, 10 Aug 2023 00:00:00 GMT"},
        )

    client = _client_with(httpx.MockTransport(handler))
    result = await client.fetch()

    assert len(seen) == 1
    request = seen[0]

    cookie_header = request.headers.get("cookie", "")
    assert "csrftoken=" in cookie_header
    cookie_token = cookie_header.split("csrftoken=")[1].split(";")[0].strip()

    form = parse_qs(request.content.decode())
    assert form["csrfmiddlewaretoken"] == [cookie_token]

    # A 64-character hex string, per secrets.token_hex(32).
    assert len(cookie_token) == 64
    int(cookie_token, 16)

    assert result.content == b"PK\x03\x04zipbytes"
    assert result.etag == '"abc123"'
    assert result.last_modified == "Wed, 10 Aug 2023 00:00:00 GMT"


async def test_fetch_generates_a_fresh_token_per_call() -> None:
    tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        tokens.append(form["csrfmiddlewaretoken"][0])
        return httpx.Response(200, content=b"zip-bytes")

    client = _client_with(httpx.MockTransport(handler))
    await client.fetch()
    await client.fetch()

    assert len(tokens) == 2
    assert tokens[0] != tokens[1]


async def test_missing_etag_and_last_modified_headers_are_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"zip-bytes")

    client = _client_with(httpx.MockTransport(handler))
    result = await client.fetch()

    assert result.etag is None
    assert result.last_modified is None


async def test_fetch_retries_then_succeeds() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(500)
        return httpx.Response(200, content=b"ok-zip")

    client = _client_with(httpx.MockTransport(handler))
    result = await client.fetch()

    assert result.content == b"ok-zip"
    assert calls["count"] == 3


async def test_fetch_raises_after_exhausting_attempts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = _client_with(httpx.MockTransport(handler), max_attempts=3)
    with pytest.raises(FeedFetchError, match="HTTP 503"):
        await client.fetch()


async def test_fetch_retries_on_transport_error() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, content=b"ok-zip")

    client = _client_with(httpx.MockTransport(handler))
    result = await client.fetch()

    assert result.content == b"ok-zip"
    assert calls["count"] == 2


async def test_empty_body_is_a_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    client = _client_with(httpx.MockTransport(handler), max_attempts=1)
    with pytest.raises(FeedFetchError, match="empty body"):
        await client.fetch()
