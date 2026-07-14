"""Tests for the park & ride endpoint and its ranking/capacity logic.

Fixture stops (tests/gtfs_fixture.py): S1 Alpha (28.60,77.00), S2 Bravo
(28.60,77.01), S3 Charlie (28.60,77.02), S4 Delta (28.60,77.03).
"""

from __future__ import annotations

from typing import Any

import httpx

from metropulse.application.commuter.park_and_ride import (
    _metro_summary,
    _summed_capacity,
)
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import StationFacility
from metropulse.infrastructure.db.commuter_repositories import (
    StationFacilityRepository,
)


async def _seed_facilities(session_factory: SessionFactory) -> None:
    async with session_factory() as session:
        async with session.begin():
            await StationFacilityRepository(session).replace_all(
                [
                    StationFacility(
                        stop_id="S1",
                        station_code="ALP",
                        elevated=True,
                        toilet=True,
                        gate_location=None,
                        match_method="name",
                        parking_lots=[
                            {"car": 100, "motorcycle": 50, "cycle": 20,
                             "operator": "Acme", "contact": "9999999999",
                             "lat": 28.6001, "lon": 77.0001},
                            {"car": 40, "motorcycle": 10, "cycle": None,
                             "operator": "Acme", "contact": "9999999999",
                             "lat": 28.6002, "lon": 77.0002},
                        ],
                    ),
                    StationFacility(
                        stop_id="S2",
                        station_code="BRV",
                        elevated=False,
                        toilet=True,
                        gate_location=None,
                        match_method="name",
                        parking_lots=[
                            {"car": 30, "motorcycle": 0, "cycle": 0,
                             "operator": "MetroPark", "contact": None,
                             "lat": None, "lon": None},
                        ],
                    ),
                    # S3 has a curated row but NO parking -> must be excluded.
                    StationFacility(
                        stop_id="S3",
                        station_code="CHR",
                        elevated=True,
                        toilet=False,
                        gate_location=None,
                        match_method="name",
                        parking_lots=None,
                    ),
                ]
            )


def test_summed_capacity_across_lots() -> None:
    lots: list[dict[str, Any]] = [{"car": 100}, {"car": 40}, {"car": None}]
    assert _summed_capacity(lots, "car") == 140
    assert _summed_capacity(None, "car") is None
    assert _summed_capacity([{"car": None}], "car") is None


def test_metro_summary_reads_line_and_changes() -> None:
    assert _metro_summary("RED_Rithala to Dilshad Garden", 0) == "Red Line, direct"
    assert _metro_summary("BLUE_A to B", 1) == "Blue Line, 1 change"
    assert _metro_summary("BLUE_A to B", 2) == "Blue Line, 2 changes"
    assert _metro_summary(None, 0) == "Metro, direct"


async def test_park_and_ride_ranks_and_sums(
    api_client: httpx.AsyncClient, loaded_session_factory: SessionFactory
) -> None:
    await _seed_facilities(loaded_session_factory)
    # Destination S4; driver sits right at S1's coordinates.
    response = await api_client.get(
        "/api/v1/park-and-ride", params={"destination": "S4", "lat": 28.60, "lon": 77.00}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["destination"] == "S4"
    cands = body["candidates"]
    # S1 and S2 have parking; S3 does not -> excluded.
    ids = {c["stop_id"] for c in cands}
    assert ids == {"S1", "S2"}
    s1 = next(c for c in cands if c["stop_id"] == "S1")
    assert s1["car_capacity"] == 140  # summed across two lots
    assert s1["motorcycle_capacity"] == 60
    assert s1["operator"] == "Acme"
    assert s1["contact"] == "9999999999"
    assert s1["metro_minutes"] is not None  # S1 -> S4 is routable on R1
    assert s1["metro_summary"] is not None
    # S1 is at the driver's exact location -> distance ~0.
    assert s1["distance_km"] == 0.0


async def test_park_and_ride_unknown_destination_404(
    api_client: httpx.AsyncClient, loaded_session_factory: SessionFactory
) -> None:
    await _seed_facilities(loaded_session_factory)
    response = await api_client.get(
        "/api/v1/park-and-ride", params={"destination": "NOPE", "lat": 28.6, "lon": 77.0}
    )
    assert response.status_code == 404
