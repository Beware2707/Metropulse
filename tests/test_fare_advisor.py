"""Tests for the fare-advisor endpoint and its discount math."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from metropulse.application.commuter.fare_advisor import _is_offpeak
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import Journey

IST = ZoneInfo("Asia/Kolkata")


async def _register(api_client: httpx.AsyncClient) -> tuple[str, dict[str, str]]:
    response = await api_client.post(
        "/api/v1/users", json={"device_id": "fare-advisor", "platform": "test"}
    )
    assert response.status_code == 201
    body = response.json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


async def _seed_journey(
    session_factory: SessionFactory, user_id: str, started_at: datetime
) -> None:
    async with session_factory() as session:
        async with session.begin():
            session.add(
                Journey(
                    user_id=user_id,
                    origin_stop_id="S1",
                    destination_stop_id="S4",
                    route_id="R1",
                    status="completed",
                    started_at=started_at,
                    ended_at=started_at + timedelta(minutes=10),
                )
            )


def test_offpeak_windows() -> None:
    assert _is_offpeak(datetime(2026, 7, 6, 7, 30, tzinfo=IST))  # before 8am
    assert _is_offpeak(datetime(2026, 7, 6, 13, 0, tzinfo=IST))  # midday
    assert _is_offpeak(datetime(2026, 7, 6, 22, 0, tzinfo=IST))  # late
    assert not _is_offpeak(datetime(2026, 7, 6, 9, 0, tzinfo=IST))  # morning peak
    assert not _is_offpeak(datetime(2026, 7, 6, 18, 30, tzinfo=IST))  # evening peak


async def test_fare_advisor_empty_history_returns_zeros(
    api_client: httpx.AsyncClient
) -> None:
    _, headers = await _register(api_client)
    response = await api_client.get("/api/v1/me/fare-advisor", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["trips"] == 0
    assert body["estimated_spend_inr"] == 0
    assert body["card_saving_inr"] == 0
    assert body["offpeak_extra_saving_inr"] == 0
    assert "estimate" in body["note"].lower() or "save" in body["note"].lower()


async def test_fare_advisor_counts_and_discounts(
    api_client: httpx.AsyncClient, loaded_session_factory: SessionFactory
) -> None:
    user_id, headers = await _register(api_client)
    now = datetime.now(IST)
    # Two peak trips + one off-peak trip in-window.
    await _seed_journey(loaded_session_factory, user_id, now - timedelta(days=1, hours=-9))
    await _seed_journey(loaded_session_factory, user_id, now.replace(hour=9) - timedelta(days=2))
    await _seed_journey(loaded_session_factory, user_id, now.replace(hour=13) - timedelta(days=3))

    response = await api_client.get("/api/v1/me/fare-advisor", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["trips"] == 3
    assert body["estimated_spend_inr"] > 0
    # Card saving is ~10% of spend.
    assert body["card_saving_inr"] > 0
    assert body["card_saving_inr"] <= body["estimated_spend_inr"]
    # At least one off-peak trip -> some off-peak extra saving.
    assert body["offpeak_extra_saving_inr"] > 0
    assert "estimate" in body["note"].lower()


async def test_fare_advisor_requires_auth(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/v1/me/fare-advisor")
    assert response.status_code == 401
