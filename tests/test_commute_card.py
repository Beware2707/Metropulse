"""Tests for next-departure lookups, the commute card, and admin stats."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from metropulse.application.commuter.last_train import LastTrainService
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.wiring import AppResources

IST = ZoneInfo("Asia/Kolkata")
SERVICE_DATE_MORNING = datetime(2026, 7, 6, 7, 30, 0, tzinfo=IST)


@pytest.fixture
def last_train() -> LastTrainService:
    return LastTrainService(timezone="Asia/Kolkata")


async def test_next_departure_basic(
    loaded_session_factory: SessionFactory, last_train: LastTrainService
) -> None:
    async with loaded_session_factory() as session:
        info = await last_train.next_departure(
            session, "S2", after=SERVICE_DATE_MORNING
        )
        assert info is not None
        assert info.trip_id == "T1"  # 08:03:30 is the first boardable departure
        assert info.departure_at == datetime(2026, 7, 6, 8, 3, 30, tzinfo=IST)

        # After T1 has left, the next option is T2 at 09:06:30.
        later = await last_train.next_departure(
            session, "S2", after=datetime(2026, 7, 6, 8, 30, 0, tzinfo=IST)
        )
        assert later is not None
        assert later.trip_id == "T2"


async def test_next_departure_rolls_to_next_service_day(
    loaded_session_factory: SessionFactory, last_train: LastTrainService
) -> None:
    async with loaded_session_factory() as session:
        late_night = datetime(2026, 7, 6, 23, 0, 0, tzinfo=IST)
        info = await last_train.next_departure(session, "S2", after=late_night)
        assert info is not None
        assert info.service_date == late_night.date() + timedelta(days=1)
        assert info.trip_id == "T1"


async def test_next_departure_respects_filters(
    loaded_session_factory: SessionFactory, last_train: LastTrainService
) -> None:
    async with loaded_session_factory() as session:
        inbound = await last_train.next_departure(
            session, "S2", after=SERVICE_DATE_MORNING, direction_id=1
        )
        assert inbound is not None
        assert inbound.trip_id == "T2"
        assert (
            await last_train.next_departure(
                session, "S2", after=SERVICE_DATE_MORNING, route_id="GHOST"
            )
            is None
        )


async def _set_home_work(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    await api_client.put(
        "/api/v1/me/favourites/stations/S1",
        json={"label": "Home", "position": 0},
        headers=auth_headers,
    )
    await api_client.put(
        "/api/v1/me/favourites/stations/S4",
        json={"label": "Work", "position": 1},
        headers=auth_headers,
    )


async def test_commute_card_requires_configuration(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await api_client.get("/api/v1/me/commute-card", headers=auth_headers)
    assert response.status_code == 409
    assert "favourite" in response.json()["detail"]


async def test_commute_card_end_to_end(
    api_client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _set_home_work(api_client, auth_headers)
    response = await api_client.get(
        "/api/v1/me/commute-card",
        params={"walk_minutes": 5},
        headers=auth_headers,
    )
    assert response.status_code == 200
    card = response.json()

    # Direction is derived from local time; endpoints are Home/Work either way.
    assert {card["origin_stop_id"], card["destination_stop_id"]} == {"S1", "S4"}
    assert card["greeting"].startswith("Good ")
    assert card["route_long_name"] == "Red Line"
    assert card["crowding"] in ("low", "moderate", "high")
    assert card["recommended_coach"] is not None
    assert card["stations_remaining"] == 3
    assert card["interchange_names"] == []
    assert card["travel_seconds"] == pytest.approx(450.0)
    if card["next_departure_at"] is not None:
        departure = datetime.fromisoformat(card["next_departure_at"])
        leave_by = datetime.fromisoformat(card["leave_by"])
        assert (departure - leave_by) == timedelta(minutes=5)
        arrival = datetime.fromisoformat(card["expected_arrival_at"])
        assert (arrival - departure).total_seconds() == pytest.approx(450.0)


async def test_commute_card_requires_auth(api_client: httpx.AsyncClient) -> None:
    assert (await api_client.get("/api/v1/me/commute-card")).status_code == 401


async def test_admin_stats(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    auth_headers: dict[str, str],
    resources: AppResources,
) -> None:
    from factories import make_vehicle
    from metropulse.domain.entities import utcnow

    await resources.vehicle_store.apply({"v1": make_vehicle("v1")}, [])
    await resources.vehicle_store.record_feed_success(utcnow())

    response = await api_client.get("/api/v1/admin/stats", headers=admin_headers)
    assert response.status_code == 200
    stats = response.json()
    assert stats["feed_status"] == "ok"
    assert stats["active_trains"] == 1
    assert stats["redis_ok"] is True
    assert stats["database_ok"] is True
    assert stats["users_total"] >= 1  # the auth_headers fixture registered one
    assert stats["users_active_15m"] >= 1
    assert stats["ws_connections"] == 0

    forbidden = await api_client.get("/api/v1/admin/stats")
    assert forbidden.status_code == 403


async def test_dashboard_page_served(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/admin/dashboard")
    assert response.status_code == 200
    assert "MetroPulse" in response.text
    assert "/api/v1/admin/stats" in response.text
