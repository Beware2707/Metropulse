"""Tests for the NCRTC (Namo Bharat / RRTS) connection loader.

The contract this pins is the honesty one. NCRTC's real feed lists 16 stops
but schedules trips to only 7. Four of the nine unserved -- Anand Vihar,
Jangpura, New Ashok Nagar, Sarai Kale Khan -- sit 35-475 m from a Delhi Metro
station of the same name. They are the stations a Delhi rider would most want
and the ones that would be a lie: showing them would put a Namo Bharat train
35 metres from someone, with no train.

So: a station with no scheduled trip never becomes a connection, however
close it is. The fixture reproduces exactly that trap.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from metropulse.application.commuter.regional_rail_loader import (
    MAX_WALK_M,
    derive_connections,
    load_regional_rail,
)
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_repositories import (
    RegionalRailConnectionRepository,
)
from metropulse.infrastructure.db.models import Stop

# Fixture stops S1..S4 sit at 28.60, 77.00/77.01/77.02/77.03.
# RAIL_NEAR is ~100 m from S2 and IS served.
# RAIL_TRAP is ~30 m from S3 and is NOT served -- the Anand Vihar case.
# RAIL_FAR is served but ~9 km away.
_STOPS = """stop_id,stop_name,stop_lat,stop_lon
R_NEAR,Bravo Rapid,28.6009,77.0100
R_TRAP,Charlie Rapid,28.6002,77.0200
R_FAR,Distant Rapid,28.6800,77.0200
"""
_ROUTES = """route_id,route_short_name,route_long_name
RT1,A - B,Towards Meerut
RT2,B - A,Towards Delhi
"""
_TRIPS = """route_id,service_id,trip_id
RT1,1,T1
RT1,1,T2
RT1,1,T4
RT2,1,T3
"""
# A regular 15-minute service at R_NEAR (06:00/06:15/06:30) plus a return
# working at 07:20, so the median gap is unambiguously 15.
# R_TRAP appears in NO trip -- the Anand Vihar case.
_STOP_TIMES = """trip_id,arrival_time,departure_time,stop_id,stop_sequence
T1,06:00:00,06:00:00,R_NEAR,1
T1,06:20:00,06:20:00,R_FAR,2
T2,06:15:00,06:15:00,R_NEAR,1
T2,06:35:00,06:35:00,R_FAR,2
T4,06:30:00,06:30:00,R_NEAR,1
T4,06:50:00,06:50:00,R_FAR,2
T3,07:00:00,07:00:00,R_FAR,1
T3,07:20:00,07:20:00,R_NEAR,2
"""


def _write_feed(tmp_path: Path, *, nested: bool = True) -> Path:
    path = tmp_path / "ncrtc.zip"
    prefix = "ncrtc_w_shapes_v1/" if nested else ""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(prefix + "stops.txt", _STOPS)
        z.writestr(prefix + "routes.txt", _ROUTES)
        z.writestr(prefix + "trips.txt", _TRIPS)
        z.writestr(prefix + "stop_times.txt", _STOP_TIMES)
    return path


def _metro_stops() -> list[Stop]:
    return [
        Stop(stop_id="S1", stop_name="Alpha", stop_lat=28.60, stop_lon=77.00),
        Stop(stop_id="S2", stop_name="Bravo", stop_lat=28.60, stop_lon=77.01),
        Stop(stop_id="S3", stop_name="Charlie", stop_lat=28.60, stop_lon=77.02),
        Stop(stop_id="S4", stop_name="Delta", stop_lat=28.60, stop_lon=77.03),
    ]


def test_unserved_station_never_becomes_a_connection(tmp_path: Path) -> None:
    """The Anand Vihar case: 30 m away, no trips, must not appear."""
    with zipfile.ZipFile(_write_feed(tmp_path)) as archive:
        result = derive_connections(archive, _metro_stops())

    names = {c.rail_station_name for c in result.connections}
    assert "Charlie Rapid" not in names, (
        "a station with no scheduled trip must never be offered, however close"
    )
    assert "Charlie Rapid" in result.unserved_stations
    assert result.served_stations == ["Bravo Rapid", "Distant Rapid"]


def test_served_and_walkable_station_becomes_a_connection(tmp_path: Path) -> None:
    with zipfile.ZipFile(_write_feed(tmp_path)) as archive:
        result = derive_connections(archive, _metro_stops())

    conn = next(c for c in result.connections if c.rail_station_name == "Bravo Rapid")
    assert conn.stop_id == "S2"
    assert conn.distance_m <= 150
    assert conn.first_departure == "06:00:00"
    assert conn.last_departure == "07:20:00"
    assert conn.headway_minutes == 15, (
        "gaps are 15/15/50 -> a typical 15-minute service"
    )
    towards = {d["towards"] for d in (conn.directions or [])}
    assert towards == {"Towards Meerut", "Towards Delhi"}, (
        "both directions are reported, so a rider knows they can come back"
    )


def test_served_but_distant_station_is_reported_not_connected(tmp_path: Path) -> None:
    """9 km away is a separate trip, not a station connection — but say so."""
    with zipfile.ZipFile(_write_feed(tmp_path)) as archive:
        result = derive_connections(archive, _metro_stops())

    assert all(c.rail_station_name != "Distant Rapid" for c in result.connections)
    reported = {u["name"] for u in result.unconnected_stations}
    assert "Distant Rapid" in reported, "no silent drops"
    far = next(u for u in result.unconnected_stations if u["name"] == "Distant Rapid")
    assert far["distance_m"] > MAX_WALK_M


def test_reads_a_flat_archive_too(tmp_path: Path) -> None:
    """The real feed nests everything under a directory; tolerate both."""
    with zipfile.ZipFile(_write_feed(tmp_path, nested=False)) as archive:
        result = derive_connections(archive, _metro_stops())
    assert len(result.connections) == 1


async def test_load_replaces_previous_rows(
    loaded_session_factory: SessionFactory, tmp_path: Path
) -> None:
    """Re-running with a newer feed replaces, so opened stations light up and
    withdrawn ones disappear."""
    path = _write_feed(tmp_path)
    await load_regional_rail(loaded_session_factory, path)
    await load_regional_rail(loaded_session_factory, path)
    async with loaded_session_factory() as session:
        rows = await RegionalRailConnectionRepository(session).for_station("S2")
        assert len(rows) == 1, "re-running must not duplicate"
        assert rows[0].service_name == "Namo Bharat"
        assert rows[0].operator == "NCRTC"
