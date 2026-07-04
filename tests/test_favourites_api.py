"""Tests for favourite stations and routes."""

from __future__ import annotations

import httpx


async def test_station_favourites_crud(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    put = await api_client.put(
        "/api/v1/me/favourites/stations/S2",
        json={"label": "Home", "position": 1},
        headers=auth_headers,
    )
    assert put.status_code == 200
    assert put.json()["label"] == "Home"

    await api_client.put(
        "/api/v1/me/favourites/stations/S3",
        json={"label": "Work", "position": 0},
        headers=auth_headers,
    )

    listing = await api_client.get("/api/v1/me/favourites/stations", headers=auth_headers)
    assert [f["stop_id"] for f in listing.json()] == ["S3", "S2"]  # ordered by position

    # Upsert updates in place.
    update = await api_client.put(
        "/api/v1/me/favourites/stations/S2",
        json={"label": "Gym", "position": 1},
        headers=auth_headers,
    )
    assert update.json()["label"] == "Gym"

    delete = await api_client.delete(
        "/api/v1/me/favourites/stations/S2", headers=auth_headers
    )
    assert delete.status_code == 204
    again = await api_client.delete(
        "/api/v1/me/favourites/stations/S2", headers=auth_headers
    )
    assert again.status_code == 404


async def test_unknown_station_favourite_404(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await api_client.put(
        "/api/v1/me/favourites/stations/GHOST", json={}, headers=auth_headers
    )
    assert response.status_code == 404


async def test_route_favourites_crud(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    put = await api_client.put("/api/v1/me/favourites/routes/R1", headers=auth_headers)
    assert put.status_code == 200
    # Idempotent.
    assert (
        await api_client.put("/api/v1/me/favourites/routes/R1", headers=auth_headers)
    ).status_code == 200

    listing = await api_client.get("/api/v1/me/favourites/routes", headers=auth_headers)
    assert [f["route_id"] for f in listing.json()] == ["R1"]

    unknown = await api_client.put(
        "/api/v1/me/favourites/routes/GHOST", headers=auth_headers
    )
    assert unknown.status_code == 404

    assert (
        await api_client.delete("/api/v1/me/favourites/routes/R1", headers=auth_headers)
    ).status_code == 204


async def test_favourites_require_auth(api_client: httpx.AsyncClient) -> None:
    assert (await api_client.get("/api/v1/me/favourites/stations")).status_code == 401
