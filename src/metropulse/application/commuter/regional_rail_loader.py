"""Derive metro <-> Namo Bharat (RRTS) connections from NCRTC's GTFS.

NCRTC publishes a GTFS feed for the Delhi-Meerut RRTS corridor. This reads it
directly -- deliberately NOT through
:mod:`metropulse.application.static_loader`, whose ``load()`` calls
``delete_all_static()`` and would replace the entire Delhi Metro dataset with
16 RRTS stops. RRTS is a different network by a different operator with its own
fares; it belongs beside the metro, not inside it.

What gets stored, and what does not:

* Only stations with **scheduled trips**. The feed lists 16 stops but runs
  trips to 7. The nine unserved are the not-yet-open Delhi extension (Anand
  Vihar, New Ashok Nagar, Sarai Kale Khan, Jangpura), the Meerut extension,
  and a depot. Four of those sit within ~100 m of a metro station of the same
  name -- exactly the ones a Delhi rider would most want, and exactly the ones
  that would be a lie today.
* Only connections within :data:`MAX_WALK_M` of a metro stop. The distance and
  a walking estimate always travel with the row so a rider judges for
  themselves; the UI calls it an interchange only when it truly is one.

Re-running replaces the table wholesale, so a newer NCRTC feed (with the Delhi
extension running) simply lights up the new connections.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from metropulse.application.commuter.geo_matching import haversine_meters
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import RegionalRailConnection
from metropulse.infrastructure.db.commuter_repositories import (
    RegionalRailConnectionRepository,
)
from metropulse.infrastructure.db.models import Stop
from metropulse.infrastructure.db.repositories import StopRepository

#: Beyond this a "connection" is really a separate trip, not a station link.
#: Kept generous (a ~20 minute walk) because the row always carries its exact
#: distance -- the honest move is to show the number, not to hide the option.
MAX_WALK_M = 1500.0

#: Below this the two stations are close enough to call an interchange.
INTERCHANGE_M = 500.0

_SERVICE_NAME = "Namo Bharat"
_OPERATOR = "NCRTC"


@dataclass
class RegionalRailResult:
    """Outcome of deriving connections from an NCRTC feed."""

    connections: list[RegionalRailConnection] = field(default_factory=list)
    served_stations: list[str] = field(default_factory=list)
    unserved_stations: list[str] = field(default_factory=list)
    #: Served stations that matched no metro stop within MAX_WALK_M.
    unconnected_stations: list[dict[str, Any]] = field(default_factory=list)


def _read_csv(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    """Read one GTFS table, tolerating the feed's nested directory prefix."""
    candidates = [n for n in archive.namelist()
                  if n.endswith("/" + name) or n == name]
    candidates = [n for n in candidates if not n.startswith("__MACOSX")]
    if not candidates:
        raise ValueError(f"{name} not found in the NCRTC archive")
    text = archive.read(candidates[0]).decode("utf-8-sig", "replace")
    return list(csv.DictReader(io.StringIO(text)))


def _median_headway_minutes(times: Sequence[str]) -> int | None:
    """Median gap between consecutive departures, in minutes.

    On an even number of gaps this takes the UPPER middle, i.e. it rounds
    towards the longer wait. Deliberate: telling a rider trains come more
    often than they do is the overclaim; a slightly conservative "every ~N
    minutes" costs them nothing.
    """
    def seconds(value: str) -> int | None:
        parts = value.split(":")
        if len(parts) != 3:
            return None
        try:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            return None

    stamps = sorted(s for s in (seconds(t) for t in times) if s is not None)
    gaps = [(b - a) // 60 for a, b in zip(stamps, stamps[1:])]
    if not gaps:
        return None
    gaps.sort()
    return gaps[len(gaps) // 2]


def _producer_name(archive: zipfile.ZipFile) -> str:
    """Who the feed says produced it -- not who operates the service.

    NCRTC's feed credits ``OpenStreetMap contributors`` as producer and names
    NCRTC only as the operating agency. Crediting NCRTC for this timetable
    would misattribute it, so the producer travels with every row.
    """
    try:
        rows = _read_csv(archive, "attributions.txt")
    except ValueError:
        return "unknown"
    for row in rows:
        name = (row.get("organization_name") or "").strip()
        if name:
            return name[:128]
    return "unknown"


def derive_connections(
    archive: zipfile.ZipFile, metro_stops: Sequence[Stop]
) -> RegionalRailResult:
    """Build connection rows from a loaded NCRTC feed and the metro stops."""
    stops = {r["stop_id"]: r for r in _read_csv(archive, "stops.txt")}
    source = _producer_name(archive)
    stop_times = _read_csv(archive, "stop_times.txt")
    trips = {r["trip_id"]: r for r in _read_csv(archive, "trips.txt")}
    routes = {r["route_id"]: r for r in _read_csv(archive, "routes.txt")}

    served_ids = {r["stop_id"] for r in stop_times if r.get("stop_id")}
    result = RegionalRailResult(
        served_stations=sorted(stops[s]["stop_name"] for s in served_ids if s in stops),
        unserved_stations=sorted(
            r["stop_name"] for sid, r in stops.items() if sid not in served_ids
        ),
    )

    # departures per (rail stop, route) -> headway and service span
    departures: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in stop_times:
        trip = trips.get(row.get("trip_id", ""))
        if trip is None or not row.get("departure_time"):
            continue
        departures[(row["stop_id"], trip.get("route_id", ""))].append(
            row["departure_time"]
        )

    for rail_id in sorted(served_ids):
        rail = stops.get(rail_id)
        if rail is None:
            continue
        try:
            rail_lat, rail_lon = float(rail["stop_lat"]), float(rail["stop_lon"])
        except (TypeError, ValueError):
            continue

        nearest: Stop | None = None
        nearest_d = float("inf")
        for stop in metro_stops:
            d = haversine_meters(rail_lat, rail_lon, stop.stop_lat, stop.stop_lon)
            if d < nearest_d:
                nearest_d, nearest = d, stop
        if nearest is None or nearest_d > MAX_WALK_M:
            result.unconnected_stations.append(
                {
                    "name": rail["stop_name"],
                    "nearest_metro": nearest.stop_name if nearest else None,
                    "distance_m": round(nearest_d) if nearest else None,
                }
            )
            continue

        per_direction: list[dict[str, Any]] = []
        all_times: list[str] = []
        for (sid, route_id), times in departures.items():
            if sid != rail_id or not times:
                continue
            times = sorted(times)
            all_times.extend(times)
            route = routes.get(route_id, {})
            per_direction.append(
                {
                    "towards": (route.get("route_long_name")
                                or route.get("route_short_name") or "").strip(),
                    "departures": len(times),
                    "first": times[0],
                    "last": times[-1],
                    "headway_minutes": _median_headway_minutes(times),
                }
            )
        per_direction.sort(key=lambda d: str(d["towards"]))
        all_times.sort()

        # The headline headway is the typical PER-DIRECTION wait. Merging
        # both directions would halve it and promise trains a rider going
        # their way cannot take.
        per_direction_headways = [
            int(d["headway_minutes"]) for d in per_direction
            if d.get("headway_minutes") is not None
        ]
        per_direction_headways.sort()
        headline_headway = (
            per_direction_headways[len(per_direction_headways) // 2]
            if per_direction_headways else None
        )

        result.connections.append(
            RegionalRailConnection(
                stop_id=nearest.stop_id,
                operator=_OPERATOR,
                service_name=_SERVICE_NAME,
                rail_station_name=rail["stop_name"],
                distance_m=round(nearest_d),
                headway_minutes=headline_headway,
                source=source,
                times_indicative=True,
                first_departure=all_times[0] if all_times else None,
                last_departure=all_times[-1] if all_times else None,
                directions=per_direction,
                match_method="coordinate",
            )
        )
    return result


async def load_regional_rail(
    session_factory: SessionFactory, zip_path: Path
) -> RegionalRailResult:
    """Replace regional_rail_connections from an NCRTC GTFS archive."""
    async with session_factory() as session:
        metro_stops = await StopRepository(session).list_all(limit=10000)

    with zipfile.ZipFile(zip_path) as archive:
        result = derive_connections(archive, metro_stops)

    async with session_factory() as session:
        async with session.begin():
            await RegionalRailConnectionRepository(session).replace_all(
                result.connections
            )
    return result
