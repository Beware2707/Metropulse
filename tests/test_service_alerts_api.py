"""Tests for service alerts: admin lifecycle, public listing, scoping."""

from __future__ import annotations

import httpx


async def _create(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    **overrides: object,
) -> dict:
    body = {
        "title": "Red Line delay",
        "description": "Trains running 10 minutes late.",
        "severity": "warning",
        **overrides,
    }
    response = await api_client.post(
        "/api/v1/admin/alerts", json=body, headers=admin_headers
    )
    assert response.status_code == 201
    return response.json()


async def test_admin_requires_key(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/admin/alerts",
        json={"title": "x", "description": "y", "severity": "info"},
    )
    assert response.status_code == 403
    wrong = await api_client.post(
        "/api/v1/admin/alerts",
        json={"title": "x", "description": "y", "severity": "info"},
        headers={"X-Admin-Key": "wrong"},
    )
    assert wrong.status_code == 403


async def test_create_and_list_active(
    api_client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    created = await _create(api_client, admin_headers, route_id="R1")
    listing = await api_client.get("/api/v1/alerts")
    assert listing.status_code == 200
    body = listing.json()
    assert body["count"] == 1
    assert body["alerts"][0]["id"] == created["id"]
    assert body["alerts"][0]["severity"] == "warning"


async def test_route_scoping(
    api_client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _create(api_client, admin_headers, route_id="R1", title="R1 only")
    await _create(api_client, admin_headers, title="Network wide")

    r1 = (await api_client.get("/api/v1/alerts", params={"route_id": "R1"})).json()
    assert r1["count"] == 2  # route-specific + network-wide

    other = (await api_client.get("/api/v1/alerts", params={"route_id": "R9"})).json()
    assert [a["title"] for a in other["alerts"]] == ["Network wide"]


async def test_revoke_removes_from_listing(
    api_client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    created = await _create(api_client, admin_headers)
    revoke = await api_client.delete(
        f"/api/v1/admin/alerts/{created['id']}", headers=admin_headers
    )
    assert revoke.status_code == 204
    assert (await api_client.get("/api/v1/alerts")).json()["count"] == 0
    # Revoking twice is a 404.
    again = await api_client.delete(
        f"/api/v1/admin/alerts/{created['id']}", headers=admin_headers
    )
    assert again.status_code == 404


async def test_invalid_severity_rejected(
    api_client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/v1/admin/alerts",
        json={"title": "x", "description": "y", "severity": "catastrophic"},
        headers=admin_headers,
    )
    assert response.status_code == 422
