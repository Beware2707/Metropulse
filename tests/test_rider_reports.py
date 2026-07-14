"""Tests for Rider Disruption Reports: submit, windowed list, dedup count."""

from __future__ import annotations

import httpx

from metropulse.infrastructure.db.base import SessionFactory


async def _register_user(
    api_client: httpx.AsyncClient, device: str
) -> tuple[str, dict[str, str]]:
    response = await api_client.post(
        "/api/v1/users", json={"device_id": device, "platform": "test"}
    )
    assert response.status_code == 201
    body = response.json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


async def test_post_report_requires_auth(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/alerts/reports", json={"message": "delayed", "category": "delay"}
    )
    assert response.status_code == 401


async def test_post_and_list_report(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    _, headers = await _register_user(api_client, "rider-a")
    post = await api_client.post(
        "/api/v1/alerts/reports",
        headers=headers,
        json={"stop_id": "S2", "route_id": "R1", "message": "Packed platform", "category": "crowding"},
    )
    assert post.status_code == 202
    assert isinstance(post.json()["report_id"], int)

    # Public list -- no auth required.
    listing = await api_client.get("/api/v1/alerts/reports")
    assert listing.status_code == 200
    reports = listing.json()["reports"]
    assert len(reports) == 1
    report = reports[0]
    assert report["stop_id"] == "S2"
    assert report["route_id"] == "R1"
    assert report["message"] == "Packed platform"
    assert report["category"] == "crowding"
    assert report["count"] == 1
    # Never leak the reporter's identity.
    assert "user_id" not in report


async def test_reports_dedup_and_count_by_stop_category(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    _, a = await _register_user(api_client, "rider-a")
    _, b = await _register_user(api_client, "rider-b")
    _, c = await _register_user(api_client, "rider-c")

    # Three riders report crowding at S2 ...
    for headers, msg in ((a, "so full"), (b, "cannot board"), (c, "insane crowd")):
        assert (
            await api_client.post(
                "/api/v1/alerts/reports",
                headers=headers,
                json={"stop_id": "S2", "message": msg, "category": "crowding"},
            )
        ).status_code == 202
    # ... and one reports a delay at S2 (different category) ...
    assert (
        await api_client.post(
            "/api/v1/alerts/reports",
            headers=a,
            json={"stop_id": "S2", "message": "train late", "category": "delay"},
        )
    ).status_code == 202
    # ... and one reports crowding at S3 (different stop).
    assert (
        await api_client.post(
            "/api/v1/alerts/reports",
            headers=b,
            json={"stop_id": "S3", "message": "busy", "category": "crowding"},
        )
    ).status_code == 202

    reports = (await api_client.get("/api/v1/alerts/reports")).json()["reports"]
    by_key = {(r["stop_id"], r["category"]): r for r in reports}
    # Three distinct (stop, category) groups.
    assert len(reports) == 3
    assert by_key[("S2", "crowding")]["count"] == 3
    assert by_key[("S2", "delay")]["count"] == 1
    assert by_key[("S3", "crowding")]["count"] == 1
    # The S2/crowding representative is the newest message in that group.
    assert by_key[("S2", "crowding")]["message"] == "insane crowd"


async def test_reports_window_excludes_old(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    _, headers = await _register_user(api_client, "rider-a")
    await api_client.post(
        "/api/v1/alerts/reports",
        headers=headers,
        json={"stop_id": "S2", "message": "now", "category": "delay"},
    )
    # A 0-length window (below the ge=1 floor) is rejected; a 1-minute window
    # still includes the just-created report.
    assert (
        await api_client.get("/api/v1/alerts/reports?since_minutes=0")
    ).status_code == 422
    recent = await api_client.get("/api/v1/alerts/reports?since_minutes=1")
    assert len(recent.json()["reports"]) == 1


async def test_report_rejects_bad_category_and_length(
    api_client: httpx.AsyncClient,
) -> None:
    _, headers = await _register_user(api_client, "rider-a")
    assert (
        await api_client.post(
            "/api/v1/alerts/reports",
            headers=headers,
            json={"message": "hi", "category": "nonsense"},
        )
    ).status_code == 422
    assert (
        await api_client.post(
            "/api/v1/alerts/reports",
            headers=headers,
            json={"message": "", "category": "delay"},
        )
    ).status_code == 422
    assert (
        await api_client.post(
            "/api/v1/alerts/reports",
            headers=headers,
            json={"message": "x" * 281, "category": "delay"},
        )
    ).status_code == 422


async def test_rider_reports_are_separate_from_operator_alerts(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    """A rider report must not appear in the authoritative operator feed."""
    _, headers = await _register_user(api_client, "rider-a")
    await api_client.post(
        "/api/v1/alerts/reports",
        headers=headers,
        json={"stop_id": "S2", "message": "crowded", "category": "crowding"},
    )
    operator = await api_client.get("/api/v1/alerts")
    assert operator.status_code == 200
    assert operator.json()["count"] == 0
