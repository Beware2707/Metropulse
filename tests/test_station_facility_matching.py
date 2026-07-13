"""Tests for the station-facility name/coordinate matching algorithm and
the GET /stations/{id}/facilities endpoint.

Uses the standard GTFS fixture (tests/gtfs_fixture.py): S1 Alpha (28.60,
77.00), S2 Bravo (28.60, 77.01), S3 Charlie (28.60, 77.02), S4 Delta
(28.60, 77.03).
"""

from __future__ import annotations

from typing import Sequence

import httpx

from metropulse.application.commuter.station_facility_loader import (
    MatchResult,
    match_facility_rows,
)
from metropulse.infrastructure.db.commuter_models import StationFacility
from metropulse.infrastructure.db.commuter_repositories import StationFacilityRepository
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.models import Stop
from metropulse.infrastructure.db.repositories import StopRepository


def _row(
    station_name: str,
    *,
    station_code: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    elevated: int | None = None,
    toilet: int | None = None,
    gate_location: str | None = None,
    parking_cycle: int | None = None,
    parking_motorcycle: int | None = None,
    parking_car: int | None = None,
    contractor: str | None = None,
    contact_number: str | None = None,
    parking_lat: float | None = None,
    parking_lon: float | None = None,
) -> dict[str, object | None]:
    return {
        "station_name": station_name,
        "station_code": station_code,
        "elevated": elevated,
        "toilet": toilet,
        "parking_available": 1 if parking_car else 0,
        "parking_cycle": parking_cycle,
        "parking_motorcycle": parking_motorcycle,
        "parking_car": parking_car,
        "gate_location": gate_location,
        "lat": lat,
        "lon": lon,
        "contractor": contractor,
        "contact_number": contact_number,
        "parking_lat": parking_lat,
        "parking_lon": parking_lon,
    }


async def _fixture_stops(loaded_session_factory: SessionFactory) -> Sequence[Stop]:
    async with loaded_session_factory() as session:
        return await StopRepository(session).list_all()


async def test_exact_name_match(loaded_session_factory: SessionFactory) -> None:
    stops = await _fixture_stops(loaded_session_factory)
    rows = [_row("Alpha", station_code="ALP", lat=28.60, lon=77.00)]
    result = match_facility_rows(rows, stops)
    assert result.name_matched == 1
    assert result.coordinate_matched == 0
    assert not result.unmatched
    assert result.facilities[0].stop_id == "S1"
    assert result.facilities[0].match_method == "name"


async def test_punctuation_case_variant_matches_same_stop(
    loaded_session_factory: SessionFactory,
) -> None:
    stops = await _fixture_stops(loaded_session_factory)
    rows = [_row("  BRAVO!!  ", station_code="BRV", lat=28.60, lon=77.01)]
    result = match_facility_rows(rows, stops)
    assert result.name_matched == 1
    assert result.facilities[0].stop_id == "S2"
    assert result.facilities[0].match_method == "name"


async def test_coordinate_fallback_match(loaded_session_factory: SessionFactory) -> None:
    stops = await _fixture_stops(loaded_session_factory)
    # Name doesn't match anything, but coordinates sit ~10m from S3 Charlie
    # (28.60, 77.02) -- well within the 500m fallback radius.
    rows = [_row("Charlie Renamed Station", lat=28.60005, lon=77.02005)]
    result = match_facility_rows(rows, stops)
    assert result.name_matched == 0
    assert result.coordinate_matched == 1
    assert not result.unmatched
    assert result.facilities[0].stop_id == "S3"
    assert result.facilities[0].match_method == "coordinate"


async def test_unmatched_row_reported_not_dropped(
    loaded_session_factory: SessionFactory,
) -> None:
    stops = await _fixture_stops(loaded_session_factory)
    # Bad name, and coordinates far (~1 degree, >100km) from every fixture stop.
    rows = [_row("Nonexistent Junction", station_code="ZZZ", lat=29.60, lon=78.50)]
    result = match_facility_rows(rows, stops)
    assert result.name_matched == 0
    assert result.coordinate_matched == 0
    assert not result.facilities
    assert len(result.unmatched) == 1
    assert result.unmatched[0]["station_name"] == "Nonexistent Junction"
    assert result.unmatched[0]["station_code"] == "ZZZ"


async def test_multi_row_parking_merge(loaded_session_factory: SessionFactory) -> None:
    stops = await _fixture_stops(loaded_session_factory)
    rows = [
        _row(
            "Delta",
            station_code="DLT",
            lat=28.60,
            lon=77.03,
            elevated=1,
            toilet=1,
            gate_location="Near Gate 01",
            parking_cycle=10,
            parking_motorcycle=20,
            parking_car=5,
            contractor="Acme Parking",
            contact_number="9999999999",
            parking_lat=28.6001,
            parking_lon=77.0301,
        ),
        _row(
            "Delta",
            station_code="DLT",
            lat=28.60,
            lon=77.03,
            gate_location="Near Gate 02",
            parking_cycle=3,
            parking_motorcycle=7,
            parking_car=2,
            contractor="Acme Parking",
            contact_number="9999999999",
            parking_lat=28.6002,
            parking_lon=77.0302,
        ),
    ]
    result = match_facility_rows(rows, stops)
    assert len(result.facilities) == 1
    assert result.name_matched == 1
    facility = result.facilities[0]
    assert facility.stop_id == "S4"
    assert facility.parking_lots is not None
    assert len(facility.parking_lots) == 2
    lots_by_car = sorted(facility.parking_lots, key=lambda lot: lot["car"])
    assert lots_by_car[0]["car"] == 2
    assert lots_by_car[1]["car"] == 5


async def test_zero_capacity_without_parking_available_yields_no_parking_lot(
    loaded_session_factory: SessionFactory,
) -> None:
    """The source sheet stores an explicit 0 (not a blank cell) in every
    capacity column for stations with no parking -- these must not be
    mistaken for real parking data (regression: an earlier loader version
    read "field is not None" and treated 0 as "has data", fabricating a
    phantom "0 cars - 0 bikes" lot for ~46% of real stations)."""
    stops = await _fixture_stops(loaded_session_factory)
    rows = [
        _row(
            "Alpha",
            station_code="ALP",
            lat=28.60,
            lon=77.00,
            parking_cycle=0,
            parking_motorcycle=0,
            parking_car=0,
        )
    ]
    result = match_facility_rows(rows, stops)
    assert result.facilities[0].parking_lots is None


async def test_result_is_dataclass_shape() -> None:
    # Cheap smoke test that MatchResult's shape hasn't drifted (all four
    # fields the CLI/tests rely on are present).
    result = MatchResult(facilities=[], unmatched=[], name_matched=0, coordinate_matched=0)
    assert result.facilities == []
    assert result.unmatched == []
    assert result.name_matched == 0
    assert result.coordinate_matched == 0


async def test_facilities_api_seeded_returns_200(
    api_client: httpx.AsyncClient, loaded_session_factory: SessionFactory
) -> None:
    async with loaded_session_factory() as session:
        async with session.begin():
            await StationFacilityRepository(session).replace_all(
                [
                    StationFacility(
                        stop_id="S1",
                        station_code="ALP",
                        elevated=True,
                        toilet=True,
                        gate_location="Near Gate 01",
                        parking_lots=[
                            {
                                "cycle": 10,
                                "motorcycle": 20,
                                "car": 5,
                                "operator": "Acme Parking",
                                "contact": "9999999999",
                                "lat": 28.6001,
                                "lon": 77.0301,
                            }
                        ],
                        match_method="name",
                    )
                ]
            )

    response = await api_client.get("/api/v1/stations/S1/facilities")
    assert response.status_code == 200
    body = response.json()
    assert body["stop_id"] == "S1"
    assert body["station_code"] == "ALP"
    assert body["elevated"] is True
    assert body["toilet"] is True
    assert body["gate_location"] == "Near Gate 01"
    assert body["match_method"] == "name"
    assert body["parking_lots"] == [
        {
            "cycle": 10,
            "motorcycle": 20,
            "car": 5,
            "operator": "Acme Parking",
            "contact": "9999999999",
            "lat": 28.6001,
            "lon": 77.0301,
        }
    ]


async def test_facilities_api_unseeded_returns_404(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/stations/S2/facilities")
    assert response.status_code == 404
