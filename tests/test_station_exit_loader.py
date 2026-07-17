"""Tests for the OSM station-exit-gate loader and the enriched exits endpoint.

Fixture stops (tests/gtfs_fixture.py): S1 Alpha (28.60,77.00), S2 Bravo
(28.60,77.01), S3 Charlie (28.60,77.02), S4 Delta (28.60,77.03).
"""

from __future__ import annotations

from typing import Any

import httpx

from metropulse.application.commuter.station_exit_loader import match_gates
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import StationExit
from metropulse.infrastructure.db.commuter_repositories import StationExitRepository
from metropulse.infrastructure.db.repositories import StopRepository


def _gate(
    name: str,
    station_name: str,
    *,
    lat: float,
    lon: float,
    gate_ref: str | None = None,
    landmarks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "gate_ref": gate_ref,
        "station_name": station_name,
        "lat": lat,
        "lon": lon,
        "landmarks": landmarks or [],
    }


async def _stops(session_factory: SessionFactory) -> list[Any]:
    async with session_factory() as session:
        return list(await StopRepository(session).list_all())


async def test_name_match_and_landmark_detail(
    loaded_session_factory: SessionFactory,
) -> None:
    stops = await _stops(loaded_session_factory)
    gates = [
        _gate(
            "Alpha Metro Gate No 1", "Alpha", lat=28.60, lon=77.00, gate_ref="1",
            landmarks=[
                {"name": "Red Fort", "category": "monument", "tourist": True, "distance_m": 200},
                {"name": "City Hospital", "category": "hospital", "tourist": False, "distance_m": 90},
            ],
        )
    ]
    result = match_gates(gates, stops)
    assert result.name_matched == 1
    assert result.coordinate_matched == 0
    assert not result.unmatched
    ex = result.exits[0]
    assert ex.stop_id == "S1"
    # flat landmarks feed the recommendation engine
    assert ex.landmarks == ["Red Fort", "City Hospital"]
    # structured detail carries the tourist flag for the UI
    assert ex.payload is not None
    detail = ex.payload["landmarks_detail"]
    assert detail[0] == {"name": "Red Fort", "category": "monument", "tourist": True}
    assert ex.payload["source"] == "osm"


async def test_coordinate_fallback_and_unmatched(
    loaded_session_factory: SessionFactory,
) -> None:
    stops = await _stops(loaded_session_factory)
    gates = [
        # name won't match, but sits ~10m from S3 Charlie -> coordinate match
        _gate("Renamed Gate", "Nowhere Special", lat=28.60005, lon=77.02005),
        # bad name AND far from every stop -> unmatched, reported
        _gate("Ghost Gate", "Ghost", lat=29.9, lon=78.9),
    ]
    result = match_gates(gates, stops)
    assert result.coordinate_matched == 1
    assert result.exits[0].stop_id == "S3"
    assert len(result.unmatched) == 1
    assert result.unmatched[0]["station_name"] == "Ghost"


async def test_api_exposes_landmarks_detail_and_source(
    api_client: httpx.AsyncClient, loaded_session_factory: SessionFactory
) -> None:
    async with loaded_session_factory() as session:
        async with session.begin():
            await StationExitRepository(session).replace_all(
                [
                    StationExit(
                        stop_id="S1",
                        name="Alpha Gate 1",
                        description=None,
                        latitude=28.60,
                        longitude=77.00,
                        landmarks=["Jantar Mantar", "HDFC Bank"],
                        payload={
                            "source": "osm",
                            "gate_ref": "1",
                            "landmarks_detail": [
                                {"name": "Jantar Mantar", "category": "monument", "tourist": True},
                                {"name": "HDFC Bank", "category": "bank", "tourist": False},
                            ],
                        },
                    )
                ]
            )

    response = await api_client.get("/api/v1/stations/S1/exits")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    exit_out = body[0]
    assert exit_out["landmarks"] == ["Jantar Mantar", "HDFC Bank"]  # flat list intact
    assert exit_out["source"] == "osm"
    detail = exit_out["landmarks_detail"]
    assert detail[0]["name"] == "Jantar Mantar" and detail[0]["tourist"] is True
    assert detail[1]["tourist"] is False


async def test_replace_all_wipes_prior_exits(
    loaded_session_factory: SessionFactory,
) -> None:
    async with loaded_session_factory() as session:
        async with session.begin():
            await StationExitRepository(session).replace_all(
                [StationExit(stop_id="S1", name="Old Gate", landmarks=[], payload={})]
            )
    async with loaded_session_factory() as session:
        async with session.begin():
            await StationExitRepository(session).replace_all(
                [StationExit(stop_id="S2", name="New Gate", landmarks=[], payload={})]
            )
    async with loaded_session_factory() as session:
        rows = await StationExitRepository(session).all_exits()
        assert [r.name for r in rows] == ["New Gate"]
        assert rows[0].stop_id == "S2"
