"""Tests for the DMRC Open Transit Data loaders.

The fixture GTFS has four stops (S1 Alpha .. S4 Delta). The registry fixture
maps official codes onto them — one by name, one only by coordinates, one
resolvable nowhere — so the match paths and the no-silent-drop rule are all
exercised. Each loader's honesty-relevant behaviour is pinned:

* official gates must NOT displace OSM exits (landmarks live there);
* re-running the registry loader must not duplicate official exits;
* accessibility ``complete`` requires an actual lift edge, not just a lift;
* period strings travel with hourly/OD rows (a dated snapshot without its
  date is an overclaim);
* unresolvable destination codes are dropped, unresolvable origins reported.
"""

from __future__ import annotations

import json
from pathlib import Path

from metropulse.application.commuter.otd_loader import (
    load_accessibility,
    load_hourly,
    load_official_registry,
    load_top_destinations,
    resolve_codes,
)
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import StationExit
from metropulse.infrastructure.db.commuter_repositories import (
    StationAccessibilityRepository,
    StationExitRepository,
    StationHourlyLoadRepository,
    StationTopDestinationsRepository,
)
from metropulse.infrastructure.db.repositories import StopRepository

# Registry: ALP matches "Alpha" by name; BRV has a wrong name but sits 60 m
# from Bravo (28.60, 77.01) so it geo-matches; ZZZ resolves nowhere.
_REGISTRY = {
    "stations": [
        {"code": "ALP", "line": 1, "name": "Alpha", "kind": "Elevated",
         "interchange": False, "lat": 28.60, "lon": 77.00, "commercial_name": None},
        {"code": "BRV", "line": 1, "name": "Bravo Junction Renamed", "kind": "Underground",
         "interchange": False, "lat": 28.6005, "lon": 77.01, "commercial_name": None},
        {"code": "CHL", "line": 1, "name": "Charlie", "kind": "Elevated",
         "interchange": False, "lat": 28.60, "lon": 77.02, "commercial_name": None},
        {"code": "ZZZ", "line": 9, "name": "Nowhere Halt", "kind": "Elevated",
         "interchange": False, "lat": 12.0, "lon": 70.0, "commercial_name": None},
        # Interchanges get one code per line -- CHL and CHL-8 are both Charlie.
        {"code": "CHL-8", "line": 8, "name": "Charlie", "kind": "Underground",
         "interchange": True, "lat": 28.60, "lon": 77.02, "commercial_name": None},
    ],
    "gates": [
        {"station_code": "ALP", "gate_name": "Gate No. 1",
         "location": "Alpha Market", "lat": 28.6001, "lon": 77.0001},
        {"station_code": "BRV", "gate_name": "Gate No. 2",
         "location": "Bravo Hospital", "lat": 28.6004, "lon": 77.0101},
        {"station_code": "ZZZ", "gate_name": "Gate No. 9",
         "location": "Nowhere", "lat": 12.0, "lon": 70.0},
        # A placeholder coordinate: CHL's gate "location" is 127km away.
        {"station_code": "CHL", "gate_name": "Gate No. 4",
         "location": "Charlie Cinema", "lat": 27.2046, "lon": 77.4977},
    ],
}

_PATHWAYS = {
    "stations": [
        {  # complete: gate + lift + platform + an elevator edge touching the lift
            "code": "ALP", "name": "Alpha", "lat": 28.60, "lon": 77.00,
            "gates": [{"id": "ALP_G1", "name": "Gate 1", "lat": 28.6, "lon": 77.0}],
            "lifts": [{"id": "ALP_L1", "name": "Lift 1", "lat": 28.6, "lon": 77.0}],
            "platforms": [{"id": "ALP_P1", "name": "Platform 1", "lat": 28.6, "lon": 77.0}],
            "edges": [
                {"from": "ALP_G1", "to": "ALP_L1", "mode": 1},
                {"from": "ALP_L1", "to": "ALP_P1", "mode": 5},
            ],
        },
        {  # incomplete: has a lift but no edge touches it
            "code": "CHL", "name": "Charlie", "lat": 28.60, "lon": 77.02,
            "gates": [{"id": "CHL_G1", "name": "Gate 1", "lat": 28.6, "lon": 77.02}],
            "lifts": [{"id": "CHL_L1", "name": "Lift 1", "lat": 28.6, "lon": 77.02}],
            "platforms": [{"id": "CHL_P1", "name": "Platform 1", "lat": 28.6, "lon": 77.02}],
            "edges": [{"from": "CHL_G1", "to": "CHL_P1", "mode": 1}],
        },
    ],
    "coverage": {"lines": ["Red"]},
}

_HOURLY = {
    "period": "september_2024",
    "profiles": [
        {"station_code": "ALP", "day_kind": "weekday",
         "hourly_entries": [10] * 24, "hourly_exits": [8] * 24, "days_averaged": 21},
        {"station_code": "ALP", "day_kind": "sunday",
         "hourly_entries": [4] * 24, "hourly_exits": [3] * 24, "days_averaged": 5},
        {"station_code": "QQQ", "day_kind": "weekday",
         "hourly_entries": [1] * 24, "hourly_exits": [1] * 24, "days_averaged": 21},
        {"station_code": "CHL", "day_kind": "weekday",
         "hourly_entries": [100] * 24, "hourly_exits": [90] * 24, "days_averaged": 21},
        {"station_code": "CHL-8", "day_kind": "weekday",
         "hourly_entries": [40] * 24, "hourly_exits": [30] * 24, "days_averaged": 21},
    ],
}

_OD = {
    "period": "january_2025",
    "origins": [
        {"origin_code": "ALP", "total_out": 1000,
         "top": [
             {"dest_code": "BRV", "count": 600},
             {"dest_code": "CHL", "count": 300},
             {"dest_code": "GHOST", "count": 100},
         ]},
        {"origin_code": "QQQ", "total_out": 50,
         "top": [{"dest_code": "ALP", "count": 50}]},
        {"origin_code": "CHL", "total_out": 700,
         "top": [{"dest_code": "ALP", "count": 400},
                 {"dest_code": "CHL-8", "count": 100}]},
        {"origin_code": "CHL-8", "total_out": 300,
         "top": [{"dest_code": "ALP", "count": 200}]},
    ],
}


def _write(tmp_path: Path) -> Path:
    d = tmp_path / "otd"
    d.mkdir()
    for name, payload in (
        ("official_stations_gates.json", _REGISTRY),
        ("pathways.json", _PATHWAYS),
        ("hourly_profile.json", _HOURLY),
        ("od_top_destinations.json", _OD),
    ):
        (d / name).write_text(json.dumps(payload), encoding="utf-8")
    return d


async def test_resolve_codes_name_geo_and_unmatched(
    loaded_session_factory: SessionFactory,
) -> None:
    async with loaded_session_factory() as session:
        stops = await StopRepository(session).list_all(limit=100)
    res = resolve_codes(_REGISTRY["stations"], stops)
    assert res.code_to_stop["ALP"] == "S1"
    assert res.code_to_stop["BRV"] == "S2", "wrong name but 60m away must geo-match"
    assert res.name_matched == 3 and res.coordinate_matched == 1, (
        "ALP, CHL and CHL-8 by name; BRV by coordinates"
    )
    assert res.unmatched_codes == ["ZZZ"], "an unresolvable code is reported, not guessed"


async def test_registry_backfills_codes_and_respects_osm_exits(
    loaded_session_factory: SessionFactory, tmp_path: Path
) -> None:
    d = _write(tmp_path)
    # Simulate the OSM exits loader having already covered Alpha.
    async with loaded_session_factory() as session:
        async with session.begin():
            StationExitRepository(session).add(
                StationExit(
                    stop_id="S1", name="OSM Gate", landmarks=["Old Fort"],
                    payload={"source": "osm", "landmarks_detail": []},
                )
            )

    result = await load_official_registry(
        loaded_session_factory, d / "official_stations_gates.json"
    )
    assert result.codes_resolved == 4
    # CHL and CHL-8 both resolve to S3; the update is per stop, so 3 rows.
    assert result.stop_codes_set == 3
    assert result.codes_unmatched == ["ZZZ"]
    # Alpha already had an OSM exit -> its official gate is skipped;
    # Bravo and Charlie had none -> their official gates are added.
    assert result.official_exits_added == 2
    assert result.gates_skipped_covered == 1

    async with loaded_session_factory() as session:
        assert (await StopRepository(session).get("S1")).stop_code == "ALP"
        repo = StationExitRepository(session)
        s1_exits = await repo.exits_for("S1")
        assert [e.payload["source"] for e in s1_exits] == ["osm"], (
            "official gates must never displace landmark-rich OSM exits"
        )
        s2_exits = await repo.exits_for("S2")
        assert len(s2_exits) == 1
        assert s2_exits[0].payload["source"] == "dmrc_official"
        assert s2_exits[0].description == "Bravo Hospital"


async def test_registry_rerun_is_idempotent(
    loaded_session_factory: SessionFactory, tmp_path: Path
) -> None:
    d = _write(tmp_path)
    await load_official_registry(loaded_session_factory, d / "official_stations_gates.json")
    await load_official_registry(loaded_session_factory, d / "official_stations_gates.json")
    async with loaded_session_factory() as session:
        s2_exits = await StationExitRepository(session).exits_for("S2")
        assert len(s2_exits) == 1, "re-running must not duplicate official exits"


async def test_accessibility_complete_requires_a_lift_edge(
    loaded_session_factory: SessionFactory, tmp_path: Path
) -> None:
    d = _write(tmp_path)
    result = await load_accessibility(
        loaded_session_factory, d / "pathways.json", d / "official_stations_gates.json"
    )
    assert result.loaded == 2 and result.unmatched_codes == []
    async with loaded_session_factory() as session:
        repo = StationAccessibilityRepository(session)
        alpha = await repo.get("S1")
        assert alpha is not None and alpha.complete is True
        charlie = await repo.get("S3")
        assert charlie is not None and charlie.complete is False, (
            "a lift no edge reaches is not a step-free path"
        )


async def test_hourly_profiles_grouped_with_period(
    loaded_session_factory: SessionFactory, tmp_path: Path
) -> None:
    d = _write(tmp_path)
    result = await load_hourly(
        loaded_session_factory, d / "hourly_profile.json", d / "official_stations_gates.json"
    )
    assert result.loaded == 2, "Alpha, plus Charlie via its merged line codes"
    assert result.unmatched_codes == ["QQQ"]
    async with loaded_session_factory() as session:
        row = await StationHourlyLoadRepository(session).get("S1")
        assert row is not None
        assert row.period == "september_2024", "the data's vintage must travel with it"
        assert set(row.profiles) == {"weekday", "sunday"}
        assert row.profiles["weekday"]["entries"] == [10] * 24


async def test_top_destinations_resolve_and_drop_ghosts(
    loaded_session_factory: SessionFactory, tmp_path: Path
) -> None:
    d = _write(tmp_path)
    result = await load_top_destinations(
        loaded_session_factory, d / "od_top_destinations.json", d / "official_stations_gates.json"
    )
    assert result.loaded == 2, "Alpha, plus Charlie via its merged line codes"
    assert result.unmatched_codes == ["QQQ"]
    async with loaded_session_factory() as session:
        row = await StationTopDestinationsRepository(session).get("S1")
        assert row is not None
        assert row.period == "january_2025" and row.total_out == 1000
        names = [t["dest_name"] for t in row.top]
        assert names == ["Bravo", "Charlie"], (
            "resolvable destinations keep rank order; GHOST is dropped"
        )


async def test_hourly_interchange_codes_are_summed_not_overwritten(
    loaded_session_factory: SessionFactory, tmp_path: Path
) -> None:
    """CHL + CHL-8 are one physical station; riders feel the sum of lines."""
    d = _write(tmp_path)
    await load_hourly(
        loaded_session_factory, d / "hourly_profile.json", d / "official_stations_gates.json"
    )
    async with loaded_session_factory() as session:
        row = await StationHourlyLoadRepository(session).get("S3")
        assert row is not None
        assert row.profiles["weekday"]["entries"] == [140] * 24, (
            "per-line profiles must add up, not last-write-wins"
        )


async def test_od_interchange_codes_merge_onto_one_row(
    loaded_session_factory: SessionFactory, tmp_path: Path
) -> None:
    """Two origin codes for one stop must not violate the unique index -- and
    their outbound totals and per-destination counts must combine."""
    d = _write(tmp_path)
    await load_top_destinations(
        loaded_session_factory, d / "od_top_destinations.json", d / "official_stations_gates.json"
    )
    async with loaded_session_factory() as session:
        row = await StationTopDestinationsRepository(session).get("S3")
        assert row is not None
        assert row.total_out == 1000, "700 (CHL) + 300 (CHL-8)"
        alpha = next(t for t in row.top if t["dest_name"] == "Alpha")
        assert alpha["count"] == 600, "400 + 200 across line codes"
        assert all(t["dest_stop_id"] != "S3" for t in row.top), (
            "a flow between two codes of the same station is not a journey"
        )


async def test_placeholder_gate_coordinates_are_nulled(
    loaded_session_factory: SessionFactory, tmp_path: Path
) -> None:
    """A gate 'located' 127km away keeps its name but loses its coords."""
    d = _write(tmp_path)
    await load_official_registry(
        loaded_session_factory, d / "official_stations_gates.json"
    )
    async with loaded_session_factory() as session:
        exits = await StationExitRepository(session).exits_for("S3")
        gate = next(e for e in exits if e.name == "Gate No. 4")
        assert gate.latitude is None and gate.longitude is None, (
            "placeholder coordinates must not draw an exit in Rajasthan"
        )
        assert gate.description == "Charlie Cinema", (
            "the textual location survives -- it is what exit search matches on"
        )
