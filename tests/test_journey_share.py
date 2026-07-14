"""Tests for Share-Live-Journey: ownership, position, PII-free public view."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import Journey

# Public-view keys per the fixed API contract -- and nothing more.
_PUBLIC_KEYS = {
    "status",
    "origin_name",
    "destination_name",
    "last_lat",
    "last_lon",
    "updated_at",
    "nearest_station",
    "eta",
}


async def _register_user(
    api_client: httpx.AsyncClient, device: str
) -> tuple[str, dict[str, str]]:
    response = await api_client.post(
        "/api/v1/users", json={"device_id": device, "platform": "test"}
    )
    assert response.status_code == 201
    body = response.json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


async def _seed_active_journey(
    session_factory: SessionFactory, user_id: str, *, origin: str = "S1", destination: str = "S4"
) -> int:
    async with session_factory() as session:
        async with session.begin():
            journey = Journey(
                user_id=user_id,
                origin_stop_id=origin,
                destination_stop_id=destination,
                route_id="R1",
                status="active",
                started_at=datetime.now(UTC),
            )
            session.add(journey)
        return journey.id


async def test_create_share_for_own_active_journey(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, headers = await _register_user(api_client, "owner")
    journey_id = await _seed_active_journey(loaded_session_factory, user_id)

    response = await api_client.post(
        f"/api/v1/me/journeys/{journey_id}/share", headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["token"]
    assert body["share_url"].endswith(f"/s/{body['token']}")
    assert body["expires_at"]


async def test_create_share_is_idempotent(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, headers = await _register_user(api_client, "owner")
    journey_id = await _seed_active_journey(loaded_session_factory, user_id)

    first = await api_client.post(
        f"/api/v1/me/journeys/{journey_id}/share", headers=headers
    )
    second = await api_client.post(
        f"/api/v1/me/journeys/{journey_id}/share", headers=headers
    )
    assert first.json()["token"] == second.json()["token"]


async def test_share_404_for_someone_elses_journey(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    owner_id, _ = await _register_user(api_client, "owner")
    _, intruder_headers = await _register_user(api_client, "intruder")
    journey_id = await _seed_active_journey(loaded_session_factory, owner_id)

    response = await api_client.post(
        f"/api/v1/me/journeys/{journey_id}/share", headers=intruder_headers
    )
    assert response.status_code == 404


async def test_share_404_for_inactive_journey(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, headers = await _register_user(api_client, "owner")
    async with loaded_session_factory() as session:
        async with session.begin():
            journey = Journey(
                user_id=user_id,
                origin_stop_id="S1",
                destination_stop_id="S4",
                status="completed",
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
            )
            session.add(journey)
        journey_id = journey.id

    response = await api_client.post(
        f"/api/v1/me/journeys/{journey_id}/share", headers=headers
    )
    assert response.status_code == 404


async def test_share_requires_auth(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client, "owner")
    journey_id = await _seed_active_journey(loaded_session_factory, user_id)
    assert (
        await api_client.post(f"/api/v1/me/journeys/{journey_id}/share")
    ).status_code == 401


async def test_position_update_reflects_in_public_view(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, headers = await _register_user(api_client, "owner")
    journey_id = await _seed_active_journey(loaded_session_factory, user_id)
    token = (
        await api_client.post(f"/api/v1/me/journeys/{journey_id}/share", headers=headers)
    ).json()["token"]

    # Before any position: active, but no coordinates yet.
    pre = await api_client.get(f"/api/v1/shared-journeys/{token}")
    assert pre.status_code == 200
    assert pre.json()["last_lat"] is None
    assert pre.json()["nearest_station"] is None

    # Post a position at S2 (Bravo: 28.60, 77.01).
    pos = await api_client.post(
        f"/api/v1/me/journeys/{journey_id}/position",
        headers=headers,
        json={"lat": 28.60, "lon": 77.01},
    )
    assert pos.status_code == 202

    view = await api_client.get(f"/api/v1/shared-journeys/{token}")
    body = view.json()
    assert body["status"] == "active"
    assert body["origin_name"] == "Alpha"
    assert body["destination_name"] == "Delta"
    assert body["last_lat"] == pytest.approx(28.60)
    assert body["last_lon"] == pytest.approx(77.01)
    assert body["nearest_station"] == "Bravo"
    assert body["updated_at"] is not None


async def test_public_view_exposes_no_pii(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, headers = await _register_user(api_client, "secret-device-42")
    journey_id = await _seed_active_journey(loaded_session_factory, user_id)
    token = (
        await api_client.post(f"/api/v1/me/journeys/{journey_id}/share", headers=headers)
    ).json()["token"]
    await api_client.post(
        f"/api/v1/me/journeys/{journey_id}/position",
        headers=headers,
        json={"lat": 28.60, "lon": 77.01},
    )

    response = await api_client.get(f"/api/v1/shared-journeys/{token}")
    body = response.json()
    # Exactly the contract keys -- no user id, device, or journey id leak.
    assert set(body.keys()) == _PUBLIC_KEYS
    # The user id / device string must appear nowhere in the raw payload.
    raw = response.text
    assert user_id not in raw
    assert "secret-device-42" not in raw
    assert "user_id" not in raw
    assert "device" not in raw


async def test_unknown_token_is_404(api_client: httpx.AsyncClient) -> None:
    assert (
        await api_client.get("/api/v1/shared-journeys/does-not-exist")
    ).status_code == 404


async def test_ended_journey_reads_ended(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, headers = await _register_user(api_client, "owner")
    journey_id = await _seed_active_journey(loaded_session_factory, user_id)
    token = (
        await api_client.post(f"/api/v1/me/journeys/{journey_id}/share", headers=headers)
    ).json()["token"]

    # Complete the journey through its own endpoint.
    done = await api_client.post(
        f"/api/v1/me/journeys/{journey_id}/complete", headers=headers
    )
    assert done.status_code == 200

    view = await api_client.get(f"/api/v1/shared-journeys/{token}")
    assert view.json()["status"] == "ended"

    # Position updates are refused once the journey has ended.
    pos = await api_client.post(
        f"/api/v1/me/journeys/{journey_id}/position",
        headers=headers,
        json={"lat": 28.60, "lon": 77.01},
    )
    assert pos.status_code == 410


async def test_stop_share_marks_expired(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, headers = await _register_user(api_client, "owner")
    journey_id = await _seed_active_journey(loaded_session_factory, user_id)
    token = (
        await api_client.post(f"/api/v1/me/journeys/{journey_id}/share", headers=headers)
    ).json()["token"]

    stopped = await api_client.delete(
        f"/api/v1/me/journeys/{journey_id}/share", headers=headers
    )
    assert stopped.status_code == 200

    view = await api_client.get(f"/api/v1/shared-journeys/{token}")
    assert view.json()["status"] == "expired"

    # A stopped share no longer accepts positions.
    pos = await api_client.post(
        f"/api/v1/me/journeys/{journey_id}/position",
        headers=headers,
        json={"lat": 28.60, "lon": 77.01},
    )
    assert pos.status_code == 410


async def test_html_share_page_is_self_contained(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, headers = await _register_user(api_client, "owner")
    journey_id = await _seed_active_journey(loaded_session_factory, user_id)
    token = (
        await api_client.post(f"/api/v1/me/journeys/{journey_id}/share", headers=headers)
    ).json()["token"]

    page = await api_client.get(f"/s/{token}")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    html = page.text
    assert token in html
    assert "/api/v1/shared-journeys/" in html
    # No external asset/script hosts; only the Open-in-Maps link is outbound.
    assert "src=\"http" not in html
    assert "https://www.google.com/maps" in html
