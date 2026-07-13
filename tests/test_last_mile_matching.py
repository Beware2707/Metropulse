"""Tests for the last-mile (shared-mobility e-rickshaw) name/coordinate
matching algorithm and the GET /stations/{id}/last-mile endpoint.

Uses the standard GTFS fixture (tests/gtfs_fixture.py): S1 Alpha (28.60,
77.00), S2 Bravo (28.60, 77.01), S3 Charlie (28.60, 77.02), S4 Delta
(28.60, 77.03).
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Sequence

import httpx

from metropulse.application.commuter.last_mile_loader import (
    MatchResult,
    SharedMobilityFeed,
    match_last_mile_routes,
    read_shared_mobility_gtfs,
)
from metropulse.infrastructure.db.commuter_models import LastMileRoute
from metropulse.infrastructure.db.commuter_repositories import LastMileRouteRepository
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.models import Stop
from metropulse.infrastructure.db.repositories import StopRepository


async def _fixture_stops(loaded_session_factory: SessionFactory) -> Sequence[Stop]:
    async with loaded_session_factory() as session:
        return await StopRepository(session).list_all()


def _empty_feed() -> SharedMobilityFeed:
    return SharedMobilityFeed(
        routes={},
        trips={},
        stops={},
        stop_times_by_trip={},
        frequencies_by_trip={},
    )


def _feed(
    *,
    route_id: str = "R1",
    route_short_name: str | None = "R1",
    route_long_name: str | None = "Route One",
    trip_id: str = "T1",
    stop_time_rows: list[dict[str, str]],
    stops: dict[str, dict[str, str]],
    frequencies_row: dict[str, str] | None = None,
    include_trip: bool = True,
) -> SharedMobilityFeed:
    feed = _empty_feed()
    feed.routes[route_id] = {
        "route_id": route_id,
        "route_short_name": route_short_name or "",
        "route_long_name": route_long_name or "",
    }
    if include_trip:
        feed.trips[trip_id] = {"trip_id": trip_id, "route_id": route_id}
    feed.stops.update(stops)
    if stop_time_rows:
        feed.stop_times_by_trip[trip_id] = sorted(
            stop_time_rows, key=lambda row: int(row["stop_sequence"])
        )
    if frequencies_row is not None:
        feed.frequencies_by_trip[trip_id] = frequencies_row
    return feed


def _stop_row(stop_id: str, name: str, lat: float, lon: float) -> dict[str, str]:
    return {"stop_id": stop_id, "stop_name": name, "stop_lat": str(lat), "stop_lon": str(lon)}


def _stop_time_row(stop_id: str, sequence: int) -> dict[str, str]:
    return {"stop_id": stop_id, "stop_sequence": str(sequence)}


async def test_exact_name_match(loaded_session_factory: SessionFactory) -> None:
    stops = await _fixture_stops(loaded_session_factory)
    feed = _feed(
        stop_time_rows=[
            _stop_time_row("LM1", 1),
            _stop_time_row("LM2", 2),
        ],
        stops={
            "LM1": _stop_row("LM1", "Alpha", 28.60, 77.00),
            "LM2": _stop_row("LM2", "Market Road", 28.6005, 77.0006),
        },
        frequencies_row={
            "trip_id": "T1",
            "start_time": "06:00:00",
            "end_time": "22:00:00",
            "headway_secs": "600",
        },
    )
    result = match_last_mile_routes(feed, stops)
    assert result.name_matched == 1
    assert result.coordinate_matched == 0
    assert not result.unmatched
    route = result.routes[0]
    assert route.hub_stop_id == "S1"
    assert route.hub_match_method == "name"
    assert route.start_time == "06:00:00"
    assert route.end_time == "22:00:00"
    assert route.headway_secs == 600
    # Full ordered stop list preserved, including the hub itself at seq 1.
    assert [s["stop_id"] for s in route.stops] == ["LM1", "LM2"]
    assert [s["sequence"] for s in route.stops] == [1, 2]


async def test_coordinate_fallback_match(loaded_session_factory: SessionFactory) -> None:
    stops = await _fixture_stops(loaded_session_factory)
    # Hub name doesn't match anything, but its coordinates sit ~10m from S3
    # Charlie (28.60, 77.02) -- well within the 500m fallback radius.
    feed = _feed(
        stop_time_rows=[_stop_time_row("LM1", 1)],
        stops={"LM1": _stop_row("LM1", "Charlie Rickshaw Point", 28.60005, 77.02005)},
    )
    result = match_last_mile_routes(feed, stops)
    assert result.name_matched == 0
    assert result.coordinate_matched == 1
    assert not result.unmatched
    assert result.routes[0].hub_stop_id == "S3"
    assert result.routes[0].hub_match_method == "coordinate"


async def test_unmatched_route_reported_not_dropped(
    loaded_session_factory: SessionFactory,
) -> None:
    stops = await _fixture_stops(loaded_session_factory)
    # Bad name, and coordinates far (~1 degree, >100km) from every fixture stop.
    feed = _feed(
        route_id="R9",
        route_short_name="R9",
        stop_time_rows=[_stop_time_row("LM1", 1)],
        stops={"LM1": _stop_row("LM1", "Nonexistent Junction", 29.60, 78.50)},
    )
    result = match_last_mile_routes(feed, stops)
    assert result.name_matched == 0
    assert result.coordinate_matched == 0
    assert not result.routes
    assert len(result.unmatched) == 1
    assert result.unmatched[0]["route_id"] == "R9"
    assert result.unmatched[0]["hub_stop_name"] == "Nonexistent Junction"


async def test_route_with_no_trip_reported_unmatched(
    loaded_session_factory: SessionFactory,
) -> None:
    stops = await _fixture_stops(loaded_session_factory)
    feed = _feed(
        route_id="R9",
        stop_time_rows=[],
        stops={},
        include_trip=False,
    )
    result = match_last_mile_routes(feed, stops)
    assert not result.routes
    assert len(result.unmatched) == 1
    assert result.unmatched[0]["route_id"] == "R9"
    assert result.unmatched[0]["hub_stop_name"] is None


async def test_trip_with_no_stop_times_reported_unmatched(
    loaded_session_factory: SessionFactory,
) -> None:
    stops = await _fixture_stops(loaded_session_factory)
    feed = _feed(route_id="R9", stop_time_rows=[], stops={})
    result = match_last_mile_routes(feed, stops)
    assert not result.routes
    assert len(result.unmatched) == 1
    assert result.unmatched[0]["route_id"] == "R9"


async def test_hub_is_minimum_sequence_not_first_row_in_file(tmp_path: Path) -> None:
    """The hub must be the stop_times row with the MINIMUM stop_sequence for
    the trip -- not merely the first row encountered in stop_times.txt. This
    feed deliberately writes rows out of sequence order (seq 3, then 1, then
    2) to catch a loader that naively took stop_times[0] without sorting."""
    zip_path = tmp_path / "shared_mobility.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(
            "routes.txt", "route_id,route_short_name,route_long_name\nR1,R1,Route One\n"
        )
        archive.writestr("trips.txt", "trip_id,route_id\nT1,R1\n")
        archive.writestr(
            "stops.txt",
            "stop_id,stop_name,stop_lat,stop_lon\n"
            "LM3,Third Stop,28.6010,77.0012\n"
            "LM1,Alpha,28.60,77.00\n"
            "LM2,Second Stop,28.6005,77.0006\n",
        )
        # Out-of-order rows: sequence 3, then 1, then 2.
        archive.writestr(
            "stop_times.txt",
            "trip_id,stop_id,stop_sequence\n"
            "T1,LM3,3\n"
            "T1,LM1,1\n"
            "T1,LM2,2\n",
        )
        archive.writestr("frequencies.txt", "trip_id,start_time,end_time,headway_secs\n")

    feed = read_shared_mobility_gtfs(zip_path)
    assert [row["stop_id"] for row in feed.stop_times_by_trip["T1"]] == ["LM1", "LM2", "LM3"]

    # LM1 "Alpha" is genuinely the min-sequence (hub) stop and should match
    # S1 Alpha by name; if the loader had instead taken the first row
    # encountered in the file, it would wrongly use LM3 "Third Stop" as the
    # hub and miss the name match entirely.
    fixture_stop = Stop(
        stop_id="S1", stop_code="RED01", stop_name="Alpha", stop_lat=28.60, stop_lon=77.00
    )
    result = match_last_mile_routes(feed, [fixture_stop])
    assert result.name_matched == 1
    assert result.routes[0].hub_stop_id == "S1"
    assert [s["stop_id"] for s in result.routes[0].stops] == ["LM1", "LM2", "LM3"]


async def test_headway_secs_zero_is_preserved_not_treated_as_absent() -> None:
    """frequencies.txt can legitimately encode headway_secs as the string
    "0"; _to_int must not confuse an empty/blank field with a real zero
    (regression class: the station-facilities loader once conflated an
    explicit 0 with "no data" for parking capacity -- headway_secs=0 must
    NOT be silently coerced to None the same way)."""
    from metropulse.application.commuter.last_mile_loader import _to_int

    assert _to_int("0") == 0
    assert _to_int("") is None
    assert _to_int(None) is None


async def test_result_is_dataclass_shape() -> None:
    result = MatchResult(routes=[], unmatched=[], name_matched=0, coordinate_matched=0)
    assert result.routes == []
    assert result.unmatched == []
    assert result.name_matched == 0
    assert result.coordinate_matched == 0


async def test_last_mile_api_seeded_returns_populated_list(
    api_client: httpx.AsyncClient, loaded_session_factory: SessionFactory
) -> None:
    async with loaded_session_factory() as session:
        async with session.begin():
            await LastMileRouteRepository(session).replace_all(
                [
                    LastMileRoute(
                        route_id="R1",
                        hub_stop_id="S1",
                        hub_match_method="name",
                        route_short_name="R1",
                        route_long_name="Alpha Shuttle",
                        start_time="06:00:00",
                        end_time="22:00:00",
                        headway_secs=600,
                        stops=[
                            {"stop_id": "LM1", "name": "Alpha", "lat": 28.60, "lon": 77.00, "sequence": 1},
                            {"stop_id": "LM2", "name": "Market Road", "lat": 28.6005, "lon": 77.0006, "sequence": 2},
                        ],
                    )
                ]
            )

    response = await api_client.get("/api/v1/stations/S1/last-mile")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["route_id"] == "R1"
    assert body[0]["route_long_name"] == "Alpha Shuttle"
    assert body[0]["headway_secs"] == 600
    assert body[0]["stops"][0]["stop_id"] == "LM1"
    # hub_stop_id / hub_match_method are intentionally not exposed in the API schema.
    assert "hub_stop_id" not in body[0]
    assert "hub_match_method" not in body[0]


async def test_last_mile_api_unseeded_returns_empty_list_not_404(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/stations/S2/last-mile")
    assert response.status_code == 200
    assert response.json() == []
