"""Tests for the user feedback endpoint (Sprint 4: beta launch)."""

from __future__ import annotations

import httpx
from sqlalchemy import select

from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import Feedback


async def test_submit_feedback_is_accepted_and_persisted(
    api_client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    loaded_session_factory: SessionFactory,
) -> None:
    response = await api_client.post(
        "/api/v1/feedback",
        json={"message": "Love the app!", "category": "praise", "app_version": "1.0.0", "platform": "android"},
        headers=auth_headers,
    )
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

    async with loaded_session_factory() as session:
        rows = (await session.execute(select(Feedback))).scalars().all()
    assert len(rows) == 1
    assert rows[0].message == "Love the app!"
    assert rows[0].category == "praise"
    assert rows[0].app_version == "1.0.0"
    assert rows[0].platform == "android"


async def test_submit_feedback_without_a_category_is_fine(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/v1/feedback",
        json={"message": "The map is a bit slow to load."},
        headers=auth_headers,
    )
    assert response.status_code == 202


async def test_submit_feedback_rejects_an_invalid_category(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/v1/feedback",
        json={"message": "hello", "category": "not-a-real-category"},
        headers=auth_headers,
    )
    assert response.status_code == 422


async def test_submit_feedback_rejects_an_empty_message(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/v1/feedback", json={"message": ""}, headers=auth_headers,
    )
    assert response.status_code == 422


async def test_submit_feedback_requires_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post("/api/v1/feedback", json={"message": "hello"})
    assert response.status_code == 401
