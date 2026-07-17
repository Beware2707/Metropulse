"""Load station exit gates + nearby landmarks from an OSM-derived artifact.

``data/station_exits.json`` (built by ``tools/build_station_exits.py`` from
OpenStreetMap) lists metro gates with their coordinates and the notable POIs
near each -- tourist attractions and heritage sites flagged ``tourist``.  Each
gate is matched to a loaded GTFS stop by normalized name, falling back to the
nearest stop within 500 m, and stored as a :class:`StationExit`:

* ``landmarks`` -- the flat list of POI names (the exit-recommendation engine
  matches a user's landmark query against this).
* ``payload.landmarks_detail`` -- the structured POIs ``[{name, category,
  tourist}]`` the UI uses to flag tourist places.
* ``payload.source = "osm"`` -- so the client can credit OpenStreetMap (ODbL).

Every gate that matches no stop is reported back, never silently dropped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from metropulse.application.commuter.geo_matching import (
    haversine_meters,
    normalize_station_name,
)
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import StationExit
from metropulse.infrastructure.db.commuter_repositories import StationExitRepository
from metropulse.infrastructure.db.models import Stop
from metropulse.infrastructure.db.repositories import StopRepository

_COORDINATE_MATCH_RADIUS_M = 500.0


@dataclass
class ExitMatchResult:
    """Outcome of matching OSM gates against loaded GTFS stops."""

    exits: list[StationExit]
    unmatched: list[dict[str, Any]]
    name_matched: int
    coordinate_matched: int


def read_gates(path: Path) -> list[dict[str, Any]]:
    """Read the ``gates`` list from the OSM-derived artifact."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    gates = data.get("gates", [])
    return [g for g in gates if isinstance(g, dict)]


def match_gates(
    gates: Sequence[dict[str, Any]], gtfs_stops: Sequence[Stop]
) -> ExitMatchResult:
    """Match each gate to a GTFS stop, building StationExit rows.

    Match by exact normalized station name; failing that, by nearest stop
    within 500 m of the gate's own coordinates. Unmatched gates are reported.
    """
    name_to_stop_id: dict[str, str] = {}
    for stop in gtfs_stops:
        key = normalize_station_name(stop.stop_name)
        name_to_stop_id.setdefault(key, stop.stop_id)

    exits: list[StationExit] = []
    unmatched: list[dict[str, Any]] = []
    name_matched = 0
    coordinate_matched = 0

    for gate in gates:
        key = normalize_station_name(str(gate.get("station_name") or ""))
        stop_id = name_to_stop_id.get(key)
        method = "name" if stop_id is not None else None

        lat, lon = gate.get("lat"), gate.get("lon")
        if stop_id is None and lat is not None and lon is not None:
            nearest_id, nearest_d = _nearest_stop(float(lat), float(lon), gtfs_stops)
            if nearest_id is not None and nearest_d <= _COORDINATE_MATCH_RADIUS_M:
                stop_id, method = nearest_id, "coordinate"

        if stop_id is None or method is None:
            unmatched.append(gate)
            continue

        if method == "name":
            name_matched += 1
        else:
            coordinate_matched += 1
        exits.append(_build_exit(stop_id, gate))

    return ExitMatchResult(
        exits=exits,
        unmatched=unmatched,
        name_matched=name_matched,
        coordinate_matched=coordinate_matched,
    )


def _nearest_stop(
    lat: float, lon: float, gtfs_stops: Sequence[Stop]
) -> tuple[str | None, float]:
    best_id: str | None = None
    best_d = float("inf")
    for stop in gtfs_stops:
        d = haversine_meters(lat, lon, stop.stop_lat, stop.stop_lon)
        if d < best_d:
            best_d, best_id = d, stop.stop_id
    return best_id, best_d


def _build_exit(stop_id: str, gate: dict[str, Any]) -> StationExit:
    # OSM often has duplicate nodes for the same feature (e.g. "Kashmiri Gate"
    # x3); dedupe by name, keeping the first (highest-priority) occurrence.
    landmarks_detail: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lm in gate.get("landmarks", []):
        if not (isinstance(lm, dict) and lm.get("name")):
            continue
        key = str(lm["name"]).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        landmarks_detail.append({
            "name": lm.get("name"),
            "category": lm.get("category"),
            "tourist": bool(lm.get("tourist")),
        })
    ref = gate.get("gate_ref")
    name = gate.get("name") or (f"Gate {ref}" if ref else "Metro gate")
    lat, lon = gate.get("lat"), gate.get("lon")
    return StationExit(
        stop_id=stop_id,
        name=str(name)[:128],
        description=None,
        latitude=float(lat) if lat is not None else None,
        longitude=float(lon) if lon is not None else None,
        landmarks=[str(d["name"]) for d in landmarks_detail],
        payload={
            "source": "osm",
            "gate_ref": ref,
            "landmarks_detail": landmarks_detail,
        },
    )


async def load_station_exits(
    session_factory: SessionFactory, json_path: Path
) -> ExitMatchResult:
    """Match the OSM gates against loaded stops and replace station_exits.

    Returns the :class:`ExitMatchResult` (incl. unmatched gates) for the
    caller to report. Wipes prior exits inside one transaction.
    """
    gates = read_gates(json_path)

    async with session_factory() as session:
        stops = await StopRepository(session).list_all(limit=10000)

    result = match_gates(gates, stops)

    async with session_factory() as session:
        async with session.begin():
            await StationExitRepository(session).replace_all(result.exits)

    return result
