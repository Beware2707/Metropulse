"""Load the DMRC Open Transit Data datasets from their normalized artifacts.

Four datasets arrive from ``data/otd_normalized/`` (parsed out of the OTD
portal's raw files by ``tools``/workflow agents):

* ``official_stations_gates.json`` — DMRC's own station registry (codes,
  lines, coordinates) and 600+ official gate locations. Loading this
  backfills ``stops.stop_code`` (the join key every other DMRC dataset is
  keyed by) and adds official-gate exits for stations the OSM exit data
  doesn't cover, with ``payload.source = "dmrc_official"``.
* ``pathways.json`` — the GTFS-Pathways accessibility graph (gates, lifts,
  platforms, edges) for the lines DMRC has mapped.
* ``hourly_profile.json`` — typical hourly entries/exits per station,
  averaged from a dated ridership snapshot. The period travels with the rows.
* ``od_top_destinations.json`` — top destinations per origin from one month
  of the OD flow matrix. The period travels with the rows.

Same discipline as every loader here: match stations by normalized name with
a coordinate fallback, replace wholesale (idempotent re-runs), and report
everything unmatched — never silently drop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from metropulse.application.commuter.geo_matching import (
    haversine_meters,
    normalize_station_name,
)
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import (
    StationAccessibility,
    StationExit,
    StationHourlyLoad,
    StationTopDestinations,
)
from metropulse.infrastructure.db.commuter_repositories import (
    StationAccessibilityRepository,
    StationExitRepository,
    StationHourlyLoadRepository,
    StationTopDestinationsRepository,
)
from metropulse.infrastructure.db.models import Stop
from metropulse.infrastructure.db.repositories import StopRepository

_COORDINATE_MATCH_RADIUS_M = 500.0
# Official gate coords farther than this from their own station are treated
# as placeholders (see load_official_registry).
_GATE_SANITY_RADIUS_M = 2000.0


def _read_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


@dataclass
class CodeResolution:
    """The station-code -> GTFS stop_id mapping built from the registry."""

    code_to_stop: dict[str, str]
    code_to_name: dict[str, str]
    unmatched_codes: list[str] = field(default_factory=list)
    name_matched: int = 0
    coordinate_matched: int = 0


def resolve_codes(
    stations: Sequence[dict[str, Any]], gtfs_stops: Sequence[Stop]
) -> CodeResolution:
    """Resolve every registry station code to a loaded GTFS stop.

    By normalized name first, then by nearest stop within 500 m. Codes that
    resolve nowhere are reported, never guessed.
    """
    name_to_stop: dict[str, str] = {}
    for stop in gtfs_stops:
        name_to_stop.setdefault(normalize_station_name(stop.stop_name), stop.stop_id)

    res = CodeResolution(code_to_stop={}, code_to_name={})
    for st in stations:
        code = str(st.get("code") or "").strip()
        if not code or code in res.code_to_stop:
            continue
        res.code_to_name[code] = str(st.get("name") or code)
        stop_id = name_to_stop.get(normalize_station_name(str(st.get("name") or "")))
        if stop_id is not None:
            res.code_to_stop[code] = stop_id
            res.name_matched += 1
            continue
        lat, lon = st.get("lat"), st.get("lon")
        if lat is not None and lon is not None:
            best_id, best_d = None, float("inf")
            for stop in gtfs_stops:
                d = haversine_meters(float(lat), float(lon), stop.stop_lat, stop.stop_lon)
                if d < best_d:
                    best_d, best_id = d, stop.stop_id
            if best_id is not None and best_d <= _COORDINATE_MATCH_RADIUS_M:
                res.code_to_stop[code] = best_id
                res.coordinate_matched += 1
                continue
        res.unmatched_codes.append(code)
    return res


@dataclass
class RegistryLoadResult:
    """Outcome of loading the official station + gate registry."""

    codes_resolved: int
    codes_unmatched: list[str]
    stop_codes_set: int
    official_exits_added: int
    gates_skipped_covered: int


async def load_official_registry(
    session_factory: SessionFactory, registry_path: Path
) -> RegistryLoadResult:
    """Backfill ``stops.stop_code`` and add official-gate exits.

    Exits are only added for stations the OSM exit loader left uncovered, so
    OSM's landmark-rich exits keep priority; official rows carry
    ``payload.source = "dmrc_official"`` and are deleted and re-added on each
    run (idempotent without touching OSM rows).

    Run this BEFORE the other OTD loaders — they join through the stop codes
    it sets.
    """
    data = _read_json(registry_path)
    stations = [s for s in data.get("stations", []) if isinstance(s, dict)]
    gates = [g for g in data.get("gates", []) if isinstance(g, dict)]

    async with session_factory() as session:
        stops = await StopRepository(session).list_all(limit=10000)
    res = resolve_codes(stations, stops)
    stop_by_id = {s.stop_id: s for s in stops}

    async with session_factory() as session:
        async with session.begin():
            stop_codes_set = await StopRepository(session).set_stop_codes(
                {stop_id: code for code, stop_id in res.code_to_stop.items()}
            )

    async with session_factory() as session:
        covered = await StationExitRepository(session).covered_stop_ids(
            exclude_source="dmrc_official"
        )

    official_exits: list[StationExit] = []
    skipped = 0
    for gate in gates:
        code = str(gate.get("station_code") or "").strip()
        stop_id = res.code_to_stop.get(code)
        if stop_id is None:
            continue
        if stop_id in covered:
            skipped += 1
            continue
        lat, lon = gate.get("lat"), gate.get("lon")
        # The registry contains placeholder coordinates: whole clusters of
        # gates pinned to one point — including one in Bharatpur, Rajasthan,
        # 127 km from Delhi. A gate "coordinate" more than 2 km from its own
        # station is data entry, not geography: keep the gate (its name and
        # location description are what the exit engine matches on) but null
        # the coords rather than draw an exit in another state.
        stop = stop_by_id.get(stop_id)
        if (
            lat is not None and lon is not None and stop is not None
            and haversine_meters(float(lat), float(lon), stop.stop_lat, stop.stop_lon)
            > _GATE_SANITY_RADIUS_M
        ):
            lat = lon = None
        location = gate.get("location")
        official_exits.append(
            StationExit(
                stop_id=stop_id,
                name=str(gate.get("gate_name") or "Gate")[:128],
                description=str(location)[:512] if location else None,
                latitude=float(lat) if lat is not None else None,
                longitude=float(lon) if lon is not None else None,
                # The location description is the only landmark DMRC gives us;
                # it is official, so it is searchable.
                landmarks=[str(location)] if location else [],
                payload={"source": "dmrc_official", "landmarks_detail": []},
            )
        )

    async with session_factory() as session:
        async with session.begin():
            repo = StationExitRepository(session)
            await repo.delete_by_source("dmrc_official")
            repo.add_rows(official_exits)

    return RegistryLoadResult(
        codes_resolved=len(res.code_to_stop),
        codes_unmatched=res.unmatched_codes,
        stop_codes_set=stop_codes_set,
        official_exits_added=len(official_exits),
        gates_skipped_covered=skipped,
    )


@dataclass
class CodedLoadResult:
    """Outcome of loading a station-code-keyed OTD dataset."""

    loaded: int
    unmatched_codes: list[str]


async def load_accessibility(
    session_factory: SessionFactory, pathways_path: Path, registry_path: Path
) -> CodedLoadResult:
    """Replace station_accessibility from the pathways artifact."""
    data = _read_json(pathways_path)
    registry = _read_json(registry_path)
    async with session_factory() as session:
        stops = await StopRepository(session).list_all(limit=10000)
    res = resolve_codes(
        [s for s in registry.get("stations", []) if isinstance(s, dict)], stops
    )
    # Pathways stations may also be resolvable by their own name/coords when
    # the code is absent from the registry.
    name_to_stop: dict[str, str] = {}
    for stop in stops:
        name_to_stop.setdefault(normalize_station_name(stop.stop_name), stop.stop_id)

    rows: list[StationAccessibility] = []
    unmatched: list[str] = []
    for st in data.get("stations", []):
        if not isinstance(st, dict):
            continue
        code = str(st.get("code") or "").strip()
        stop_id = res.code_to_stop.get(code)
        method = "code"
        if stop_id is None:
            stop_id = name_to_stop.get(normalize_station_name(str(st.get("name") or "")))
            method = "name"
        if stop_id is None:
            # The parse artifact carries its own geo-resolved stop id for
            # stations whose name/code match nothing (renames, spelling).
            # Trust it only if that stop actually exists in our GTFS load.
            claimed = st.get("gtfs_stop_id")
            if claimed is not None and any(s.stop_id == str(claimed) for s in stops):
                stop_id, method = str(claimed), "artifact"
        if stop_id is None:
            unmatched.append(code or str(st.get("name")))
            continue
        gates = st.get("gates") or []
        lifts = st.get("lifts") or []
        platforms = st.get("platforms") or []
        edges = st.get("edges") or []
        # Complete = at least one gate, one lift, one platform AND edges that
        # touch a lift (the elevator link is what makes the path step-free).
        lift_ids = {lift.get("id") for lift in lifts}
        lift_edges = any(
            e.get("from") in lift_ids or e.get("to") in lift_ids for e in edges
        )
        rows.append(
            StationAccessibility(
                stop_id=stop_id,
                station_code=code or None,
                gates=gates,
                lifts=lifts,
                platforms=platforms,
                edges=edges,
                complete=bool(gates and lifts and platforms and lift_edges),
                match_method=method,
            )
        )

    async with session_factory() as session:
        async with session.begin():
            await StationAccessibilityRepository(session).replace_all(rows)
    return CodedLoadResult(loaded=len(rows), unmatched_codes=unmatched)


async def load_hourly(
    session_factory: SessionFactory, hourly_path: Path, registry_path: Path
) -> CodedLoadResult:
    """Replace station_hourly_load from the ridership artifact."""
    data = _read_json(hourly_path)
    registry = _read_json(registry_path)
    period = str(data.get("period") or "unknown")
    async with session_factory() as session:
        stops = await StopRepository(session).list_all(limit=10000)
    res = resolve_codes(
        [s for s in registry.get("stations", []) if isinstance(s, dict)], stops
    )

    by_stop: dict[str, dict[str, Any]] = {}
    unmatched: list[str] = []
    for prof in data.get("profiles", []):
        if not isinstance(prof, dict):
            continue
        code = str(prof.get("station_code") or "").strip()
        stop_id = res.code_to_stop.get(code)
        if stop_id is None:
            if code and code not in unmatched:
                unmatched.append(code)
            continue
        entry = by_stop.setdefault(
            stop_id, {"station_code": code, "profiles": {}}
        )
        # Interchange stations report one profile PER LINE CODE (Kashmere
        # Gate arrives as KGM + KGR + KG-6, all resolving to one stop). A
        # rider at the station experiences the SUM of the lines, so profiles
        # landing on an occupied day_kind are added element-wise — the naive
        # overwrite kept whichever line happened to parse last.
        incoming = {
            "entries": prof.get("hourly_entries"),
            "exits": prof.get("hourly_exits"),
            "days": prof.get("days_averaged"),
        }
        existing = entry["profiles"].get(str(prof.get("day_kind")))
        if existing is not None:
            for key in ("entries", "exits"):
                a, b = existing.get(key), incoming.get(key)
                if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
                    incoming[key] = [int(x) + int(y) for x, y in zip(a, b)]
                elif isinstance(a, list):
                    incoming[key] = a
        entry["profiles"][str(prof.get("day_kind"))] = incoming

    rows = [
        StationHourlyLoad(
            stop_id=stop_id,
            station_code=entry["station_code"] or None,
            period=period,
            profiles=entry["profiles"],
            match_method="code",
        )
        for stop_id, entry in by_stop.items()
    ]
    async with session_factory() as session:
        async with session.begin():
            await StationHourlyLoadRepository(session).replace_all(rows)
    return CodedLoadResult(loaded=len(rows), unmatched_codes=unmatched)


async def load_top_destinations(
    session_factory: SessionFactory, od_path: Path, registry_path: Path
) -> CodedLoadResult:
    """Replace station_top_destinations from the OD artifact."""
    data = _read_json(od_path)
    registry = _read_json(registry_path)
    period = str(data.get("period") or "unknown")
    async with session_factory() as session:
        stops = await StopRepository(session).list_all(limit=10000)
    res = resolve_codes(
        [s for s in registry.get("stations", []) if isinstance(s, dict)], stops
    )
    stop_name_by_id = {s.stop_id: s.stop_name for s in stops}

    # Interchange stations appear once PER LINE CODE on both axes (Kashmere
    # Gate = KGM + KGR + KG-6). Everything is merged onto the resolved stop:
    # origin rows sum their totals, and destination counts landing on the
    # same resolved stop add up. Without this the loader would try to insert
    # three rows for one stop_id (unique-index violation) and understate
    # every interchange's counts.
    merged: dict[str, dict[str, Any]] = {}
    unmatched: list[str] = []
    for origin in data.get("origins", []):
        if not isinstance(origin, dict):
            continue
        code = str(origin.get("origin_code") or "").strip()
        stop_id = res.code_to_stop.get(code)
        if stop_id is None:
            if code and code not in unmatched:
                unmatched.append(code)
            continue
        entry = merged.setdefault(
            stop_id, {"station_code": code, "total_out": 0, "dest_counts": {}}
        )
        entry["total_out"] += int(origin.get("total_out") or 0)
        for d in origin.get("top", []):
            dest_code = str(d.get("dest_code") or "").strip()
            dest_stop = res.code_to_stop.get(dest_code)
            if dest_stop is None:
                # A destination we can't resolve is dropped from the list —
                # showing a code the app can't link anywhere helps no one.
                continue
            if dest_stop == stop_id:
                continue  # a self-loop across line codes is not a journey
            entry["dest_counts"][dest_stop] = (
                entry["dest_counts"].get(dest_stop, 0) + int(d.get("count") or 0)
            )

    rows: list[StationTopDestinations] = []
    for stop_id, entry in merged.items():
        ranked = sorted(
            entry["dest_counts"].items(), key=lambda kv: (-kv[1], kv[0])
        )[:8]
        if not ranked:
            continue
        rows.append(
            StationTopDestinations(
                stop_id=stop_id,
                station_code=entry["station_code"] or None,
                period=period,
                total_out=entry["total_out"],
                top=[
                    {
                        "dest_stop_id": dest,
                        "dest_name": stop_name_by_id.get(dest, dest),
                        "count": count,
                    }
                    for dest, count in ranked
                ],
                match_method="code",
            )
        )

    async with session_factory() as session:
        async with session.begin():
            await StationTopDestinationsRepository(session).replace_all(rows)
    return CodedLoadResult(loaded=len(rows), unmatched_codes=unmatched)
