"""Tests for device registration and token auth."""

from __future__ import annotations

import httpx


async def test_register_creates_user(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/users", json={"device_id": "dev-1", "platform": "ios"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    assert body["token"]
    assert body["user_id"]


async def test_me_requires_auth(api_client: httpx.AsyncClient) -> None:
    assert (await api_client.get("/api/v1/me")).status_code == 401
    assert (
        await api_client.get("/api/v1/me", headers={"Authorization": "Bearer bogus"})
    ).status_code == 401


async def test_me_returns_profile(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await api_client.get("/api/v1/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["device_id"] == "test-device"


async def test_reregistering_rotates_token(api_client: httpx.AsyncClient) -> None:
    first = (await api_client.post("/api/v1/users", json={"device_id": "dev-2"})).json()
    second = (await api_client.post("/api/v1/users", json={"device_id": "dev-2"})).json()
    assert second["created"] is False
    assert second["user_id"] == first["user_id"]
    assert second["token"] != first["token"]

    # Old token is dead, new token works.
    old = await api_client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {first['token']}"}
    )
    assert old.status_code == 401
    new = await api_client.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {second['token']}"}
    )
    assert new.status_code == 200
