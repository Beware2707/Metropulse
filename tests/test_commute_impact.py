"""Tests for Commute Replay: per-trip and monthly impact figures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from metropulse.application.intelligence.commute_impact import (
    _ASSUMED_ROAD_SPEED_KMH,
    _CAB_BASE_FARE_RUPEES,
    _CAB_PER_KM_RUPEES,
    _CAR_CO2_KG_PER_KM,
    _METRO_CO2_KG_PER_KM,
    CommuteImpactService,
)
from metropulse.domain.exceptions import UnknownEntityError
from metropulse.domain.geometry import haversine_m
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import Journey

IST = ZoneInfo("Asia/Kolkata")
A_MONDAY = datetime(2026, 7, 6, 8, 10, 0, tzinfo=IST)

# S1 (Alpha, 28.60/77.00) -> S4 (Delta, 28.60/77.03) per tests/gtfs_fixture.py.
_S1_LAT, _S1_LON = 28.60, 77.00
_S4_LAT, _S4_LON = 28.60, 77.03
_DISTANCE_KM = haversine_m(_S1_LAT, _S1_LON, _S4_LAT, _S4_LON) / 1000.0


async def _register_user(api_client: httpx.AsyncClient) -> tuple[str, dict[str, str]]:
    response = await api_client.post(
        "/api/v1/users", json={"device_id": f"device-{id(api_client)}", "platform": "test"}
    )
    assert response.status_code == 201
    body = response.json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


async def _seed_journey(
    session_factory: SessionFactory,
    user_id: str,
    *,
    origin: str,
    destination: str,
    started_at: datetime,
    duration_seconds: float,
    status: str = "completed",
) -> None:
    async with session_factory() as session:
        async with session.begin():
            session.add(
                Journey(
                    user_id=user_id,
                    origin_stop_id=origin,
                    destination_stop_id=destination,
                    route_id="R1",
                    status=status,
                    started_at=started_at,
                    ended_at=started_at + timedelta(seconds=duration_seconds),
                )
            )


def _expected_metro_fare(distance_km: float) -> int:
    slabs = [(2.0, 10), (5.0, 20), (12.0, 30), (21.0, 40), (32.0, 50)]
    for max_km, rupees in slabs:
        if distance_km <= max_km:
            return rupees
    return 60


# --- Single trip -----------------------------------------------------------------


async def test_latest_trip_requires_history(loaded_session_factory: SessionFactory) -> None:
    service = CommuteImpactService()
    async with loaded_session_factory() as session:
        with pytest.raises(UnknownEntityError):
            await service.latest_trip(session, "nobody")


async def test_latest_trip_computes_documented_figures(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client)
    duration_seconds = 500.0
    await _seed_journey(
        loaded_session_factory,
        user_id,
        origin="S1",
        destination="S4",
        started_at=A_MONDAY,
        duration_seconds=duration_seconds,
    )

    service = CommuteImpactService()
    async with loaded_session_factory() as session:
        replay = await service.latest_trip(session, user_id)

    assert replay.origin_stop_id == "S1"
    assert replay.origin_name == "Alpha"
    assert replay.destination_stop_id == "S4"
    assert replay.destination_name == "Delta"
    assert replay.duration_seconds == pytest.approx(duration_seconds)
    assert replay.distance_km == pytest.approx(_DISTANCE_KM, abs=0.05)

    # Recomputed from the same full-precision distance the service itself
    # uses internally (replay.distance_km is the *rounded* display value).
    expected_metro_fare = _expected_metro_fare(_DISTANCE_KM)
    assert replay.metro_fare_rupees == expected_metro_fare

    expected_cab_fare = round(_CAB_BASE_FARE_RUPEES + _CAB_PER_KM_RUPEES * _DISTANCE_KM)
    assert replay.estimated_cab_fare_rupees == expected_cab_fare
    assert replay.money_saved_rupees == max(0, expected_cab_fare - expected_metro_fare)

    expected_road_seconds = _DISTANCE_KM / _ASSUMED_ROAD_SPEED_KMH * 3600.0
    assert replay.time_saved_seconds == pytest.approx(
        max(0.0, expected_road_seconds - duration_seconds), abs=1.0
    )

    expected_co2 = _DISTANCE_KM * (_CAR_CO2_KG_PER_KM - _METRO_CO2_KG_PER_KM)
    assert replay.co2_saved_kg == pytest.approx(expected_co2, abs=0.02)


async def test_latest_trip_never_reports_negative_savings(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    """A very slow trip must clamp to zero, never show negative "savings"."""
    user_id, _ = await _register_user(api_client)
    await _seed_journey(
        loaded_session_factory,
        user_id,
        origin="S1",
        destination="S4",
        started_at=A_MONDAY,
        duration_seconds=3 * 3600.0,  # much slower than any road estimate
    )

    service = CommuteImpactService()
    async with loaded_session_factory() as session:
        replay = await service.latest_trip(session, user_id)

    assert replay.time_saved_seconds == 0.0
    assert replay.co2_saved_kg >= 0.0
    assert replay.money_saved_rupees >= 0


async def test_latest_trip_api(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, headers = await _register_user(api_client)

    fresh = await api_client.get("/api/v1/me/replay/latest-trip", headers=headers)
    assert fresh.status_code == 404

    await _seed_journey(
        loaded_session_factory,
        user_id,
        origin="S1",
        destination="S4",
        started_at=A_MONDAY,
        duration_seconds=500.0,
    )
    response = await api_client.get("/api/v1/me/replay/latest-trip", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["origin_name"] == "Alpha"
    assert body["destination_name"] == "Delta"
    assert body["metro_fare_rupees"] > 0

    assert (await api_client.get("/api/v1/me/replay/latest-trip")).status_code == 401


# --- Monthly summary ---------------------------------------------------------------


async def test_monthly_summary_empty_is_not_an_error(
    loaded_session_factory: SessionFactory,
) -> None:
    service = CommuteImpactService()
    async with loaded_session_factory() as session:
        summary = await service.monthly_summary(session, "nobody", A_MONDAY)
    assert summary.trip_count == 0
    assert summary.total_distance_km == 0
    assert summary.total_money_saved_rupees == 0
    assert summary.total_co2_saved_kg == 0


async def test_monthly_summary_aggregates_trips_in_window(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client)
    for day_offset in (1, 3, 5):
        await _seed_journey(
            loaded_session_factory,
            user_id,
            origin="S1",
            destination="S4",
            started_at=A_MONDAY - timedelta(days=day_offset),
            duration_seconds=500.0,
        )

    service = CommuteImpactService(monthly_window_days=30.0)
    async with loaded_session_factory() as session:
        summary = await service.monthly_summary(session, user_id, A_MONDAY)

    assert summary.trip_count == 3
    assert summary.total_distance_km == pytest.approx(_DISTANCE_KM * 3, abs=0.2)
    assert summary.total_money_saved_rupees >= 0
    assert summary.total_co2_saved_kg >= 0


async def test_monthly_summary_excludes_trips_outside_window(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, _ = await _register_user(api_client)
    await _seed_journey(
        loaded_session_factory,
        user_id,
        origin="S1",
        destination="S4",
        started_at=A_MONDAY - timedelta(days=45),  # well outside a 30-day window
        duration_seconds=500.0,
    )

    service = CommuteImpactService(monthly_window_days=30.0)
    async with loaded_session_factory() as session:
        summary = await service.monthly_summary(session, user_id, A_MONDAY)

    assert summary.trip_count == 0


async def test_monthly_replay_api(
    loaded_session_factory: SessionFactory, api_client: httpx.AsyncClient
) -> None:
    user_id, headers = await _register_user(api_client)
    # The endpoint uses the real wall clock, so seed relative to right now
    # rather than a fixed date — otherwise this test's pass/fail would
    # depend on how far "now" has drifted from the fixture calendar.
    await _seed_journey(
        loaded_session_factory,
        user_id,
        origin="S1",
        destination="S4",
        started_at=datetime.now(UTC) - timedelta(days=2),
        duration_seconds=500.0,
    )
    response = await api_client.get("/api/v1/me/replay/monthly", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["trip_count"] == 1

    assert (await api_client.get("/api/v1/me/replay/monthly")).status_code == 401
