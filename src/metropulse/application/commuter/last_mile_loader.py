"""Load curated shared-mobility (e-rickshaw) last-mile routes from a Delhi
Transport Stack GTFS feed (shared_mobility_gtfs_v1.zip) and match each
route's hub stop to a loaded metro GTFS stop.

This is a SEPARATE, unrelated GTFS feed from DMRC's own static feed: it has
its own route_id/stop_id/trip_id space (which may collide with DMRC's), and
its data is curated reference data, not wholesale-replaceable core transit
data (see the module docstring's rule 1 in
:mod:`metropulse.infrastructure.db.commuter_models`). So this loader
performs its own lightweight parse of routes.txt/trips.txt/stops.txt/
stop_times.txt/frequencies.txt -- it intentionally does NOT reuse
:func:`metropulse.application.static_loader.read_gtfs_zip` or
:class:`~metropulse.application.static_loader.GtfsStaticLoader`, and it
never writes to the core GTFS tables.

Each route's hub stop -- the stop_times row with the minimum stop_sequence
for that route's (single) trip -- is matched against the metro's loaded
GTFS stops by normalized name, falling back to nearest GTFS stop by
coordinate for hubs whose name doesn't line up. Every unmatched route is
reported back to the caller -- never silently dropped -- via
:attr:`MatchResult.unmatched`.

Pure logic + I/O only: no FastAPI/CLI imports here, so the matching
algorithm stays unit-testable in isolation.

Deliberately NOT parsed for v1: calendar.txt (has a malformed start_date in
this feed), calendar_dates.txt, shapes.txt -- service-day validity isn't
needed for a "what last-mile options exist near this station" display.
"""

from __future__ import annotations

import csv
import io
import logging
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from metropulse.application.commuter.geo_matching import haversine_meters, normalize_station_name
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import LastMileRoute
from metropulse.infrastructure.db.commuter_repositories import LastMileRouteRepository
from metropulse.infrastructure.db.models import Stop
from metropulse.infrastructure.db.repositories import StopRepository

logger = logging.getLogger(__name__)

_COORDINATE_MATCH_RADIUS_M = 500.0


@dataclass
class SharedMobilityFeed:
    """Raw, string-typed rows from shared_mobility_gtfs_v1.zip.

    Deliberately only the five files this feature needs (see the module
    docstring) -- calendar.txt/calendar_dates.txt/shapes.txt are not read.
    """

    routes: dict[str, dict[str, str]]
    trips: dict[str, dict[str, str]]
    stops: dict[str, dict[str, str]]
    stop_times_by_trip: dict[str, list[dict[str, str]]]
    frequencies_by_trip: dict[str, dict[str, str]]


def read_shared_mobility_gtfs(zip_path: Path) -> SharedMobilityFeed:
    """Read routes/trips/stops/stop_times/frequencies from the feed ZIP.

    ``stop_times_by_trip`` values are sorted by ``stop_sequence``, so index
    0 is always the hub stop. ``frequencies_by_trip`` holds one row per
    trip; if a trip unexpectedly has more than one frequencies.txt row, the
    first is kept and a warning is logged -- never a crash, never a silent
    arbitrary pick.
    """
    with zipfile.ZipFile(zip_path) as archive:
        names = {Path(n).name: n for n in archive.namelist()}

        def _read_csv(filename: str) -> list[dict[str, str]]:
            member = names.get(filename)
            if member is None:
                return []
            with archive.open(member) as handle:
                text = io.TextIOWrapper(handle, encoding="utf-8-sig", newline="")
                reader = csv.DictReader(text)
                if reader.fieldnames:
                    reader.fieldnames = [name.strip() for name in reader.fieldnames]
                return [
                    {k: (v or "").strip() for k, v in row.items() if k is not None}
                    for row in reader
                ]

        route_rows = _read_csv("routes.txt")
        trip_rows = _read_csv("trips.txt")
        stop_rows = _read_csv("stops.txt")
        stop_time_rows = _read_csv("stop_times.txt")
        frequency_rows = _read_csv("frequencies.txt")

    routes = {row["route_id"]: row for row in route_rows}
    trips = {row["trip_id"]: row for row in trip_rows}
    stops = {row["stop_id"]: row for row in stop_rows}

    stop_times_by_trip: dict[str, list[dict[str, str]]] = {}
    for row in stop_time_rows:
        stop_times_by_trip.setdefault(row["trip_id"], []).append(row)
    for rows in stop_times_by_trip.values():
        rows.sort(key=lambda row: int(row["stop_sequence"]))

    frequencies_by_trip: dict[str, dict[str, str]] = {}
    for row in frequency_rows:
        trip_id = row["trip_id"]
        if trip_id in frequencies_by_trip:
            logger.warning(
                "trip %s has more than one frequencies.txt row; using the first", trip_id
            )
            continue
        frequencies_by_trip[trip_id] = row

    return SharedMobilityFeed(
        routes=routes,
        trips=trips,
        stops=stops,
        stop_times_by_trip=stop_times_by_trip,
        frequencies_by_trip=frequencies_by_trip,
    )


@dataclass
class MatchResult:
    """Outcome of matching shared-mobility routes against loaded GTFS stops."""

    routes: list[LastMileRoute]
    unmatched: list[dict[str, Any]]
    name_matched: int
    coordinate_matched: int


def match_last_mile_routes(
    feed: SharedMobilityFeed, gtfs_stops: Sequence[Stop]
) -> MatchResult:
    """Match each shared-mobility route's hub stop to a GTFS stop.

    1. Each route_id is resolved to its (single) trip_id, and that trip's
       hub stop -- the stop_times row with the minimum stop_sequence -- is
       looked up in the feed's own stops.txt.
    2. The hub's name is matched by exact normalized-name lookup against
       the GTFS stops; failing that, by nearest GTFS stop within 500 meters
       of the hub's own lat/lon.
    3. Routes matching neither way are appended to ``unmatched`` with the
       hub's raw name/coordinates, never dropped silently. A route with no
       trip, or a trip with no stop_times, is also reported as unmatched
       rather than raising.
    """
    name_to_stop_id: dict[str, str] = {}
    for stop in gtfs_stops:
        key = normalize_station_name(stop.stop_name)
        if key not in name_to_stop_id:
            name_to_stop_id[key] = stop.stop_id

    route_id_to_trip_id: dict[str, str] = {}
    for trip_id, trip_row in feed.trips.items():
        route_id_to_trip_id.setdefault(trip_row["route_id"], trip_id)

    routes: list[LastMileRoute] = []
    unmatched: list[dict[str, Any]] = []
    name_matched = 0
    coordinate_matched = 0

    for route_id, route_row in feed.routes.items():
        route_short_name = route_row.get("route_short_name") or None
        route_long_name = route_row.get("route_long_name") or None

        route_trip_id = route_id_to_trip_id.get(route_id)
        stop_time_rows = (
            feed.stop_times_by_trip.get(route_trip_id, []) if route_trip_id else []
        )
        if not stop_time_rows:
            unmatched.append(
                {
                    "route_id": route_id,
                    "route_short_name": route_short_name,
                    "hub_stop_name": None,
                    "hub_stop_lat": None,
                    "hub_stop_lon": None,
                }
            )
            continue

        hub_row = stop_time_rows[0]
        hub_stop_row = feed.stops.get(hub_row["stop_id"])
        hub_name = hub_stop_row.get("stop_name") if hub_stop_row else None
        hub_lat = _to_float(hub_stop_row.get("stop_lat")) if hub_stop_row else None
        hub_lon = _to_float(hub_stop_row.get("stop_lon")) if hub_stop_row else None

        matched_stop_id: str | None = None
        match_method: str | None = None

        if hub_name:
            matched_stop_id = name_to_stop_id.get(normalize_station_name(hub_name))
            if matched_stop_id is not None:
                match_method = "name"

        if matched_stop_id is None and hub_lat is not None and hub_lon is not None:
            nearest_stop_id, nearest_distance = _nearest_stop(hub_lat, hub_lon, gtfs_stops)
            if nearest_stop_id is not None and nearest_distance <= _COORDINATE_MATCH_RADIUS_M:
                matched_stop_id = nearest_stop_id
                match_method = "coordinate"

        if matched_stop_id is None or match_method is None:
            unmatched.append(
                {
                    "route_id": route_id,
                    "route_short_name": route_short_name,
                    "hub_stop_name": hub_name,
                    "hub_stop_lat": hub_lat,
                    "hub_stop_lon": hub_lon,
                }
            )
            continue

        if match_method == "name":
            name_matched += 1
        else:
            coordinate_matched += 1

        assert route_trip_id is not None  # a matched route always resolved a trip above
        frequencies_row = feed.frequencies_by_trip.get(route_trip_id)
        routes.append(
            LastMileRoute(
                route_id=route_id,
                hub_stop_id=matched_stop_id,
                hub_match_method=match_method,
                route_short_name=route_short_name,
                route_long_name=route_long_name,
                start_time=frequencies_row.get("start_time") if frequencies_row else None,
                end_time=frequencies_row.get("end_time") if frequencies_row else None,
                headway_secs=(
                    _to_int(frequencies_row.get("headway_secs")) if frequencies_row else None
                ),
                stops=_build_stops(stop_time_rows, feed.stops),
            )
        )

    return MatchResult(
        routes=routes,
        unmatched=unmatched,
        name_matched=name_matched,
        coordinate_matched=coordinate_matched,
    )


def _nearest_stop(
    lat: float, lon: float, gtfs_stops: Sequence[Stop]
) -> tuple[str | None, float]:
    """Nearest GTFS stop to a single lat/lon point."""
    best_stop_id: str | None = None
    best_distance = math.inf
    for stop in gtfs_stops:
        distance = haversine_meters(lat, lon, stop.stop_lat, stop.stop_lon)
        if distance < best_distance:
            best_distance = distance
            best_stop_id = stop.stop_id
    return best_stop_id, best_distance


def _build_stops(
    stop_time_rows: Sequence[dict[str, str]], stops_by_id: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    """The route's full ordered stop list, resolved against the feed's own
    stops.txt (NOT the metro Stop table -- these are the e-rickshaw's own
    stop coordinates)."""
    ordered: list[dict[str, Any]] = []
    for row in stop_time_rows:
        stop_id = row["stop_id"]
        stop_row = stops_by_id.get(stop_id)
        ordered.append(
            {
                "stop_id": stop_id,
                "name": stop_row.get("stop_name") if stop_row else None,
                "lat": _to_float(stop_row.get("stop_lat")) if stop_row else None,
                "lon": _to_float(stop_row.get("stop_lon")) if stop_row else None,
                "sequence": int(row["stop_sequence"]),
            }
        )
    return ordered


def _to_float(value: str | None) -> float | None:
    return None if not value else float(value)


def _to_int(value: str | None) -> int | None:
    return None if not value else int(value)


async def load_last_mile_routes(
    session_factory: SessionFactory, zip_path: Path
) -> MatchResult:
    """Match the shared-mobility feed against loaded GTFS stops and replace
    the table.

    Reads every :class:`Stop` row (via :class:`StopRepository`), parses and
    matches the shared-mobility feed, then wholesale-replaces
    ``last_mile_routes`` inside a single transaction (see the model's
    docstring). Always returns the full :class:`MatchResult` -- including
    ``unmatched`` -- so the caller can report exactly what needs manual
    attention.
    """
    async with session_factory() as session:
        gtfs_stops = await StopRepository(session).list_all()

    feed = read_shared_mobility_gtfs(zip_path)
    result = match_last_mile_routes(feed, gtfs_stops)

    async with session_factory() as session:
        async with session.begin():
            await LastMileRouteRepository(session).replace_all(result.routes)

    return result
