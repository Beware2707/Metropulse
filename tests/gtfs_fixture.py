"""Reusable GTFS static fixture: a small, internally consistent dataset.

One route (R1) with four stops (S1..S4) evenly spaced along latitude 28.60
between longitudes 77.00 and 77.03, one shape per direction, two trips
(T1 outbound, T2 inbound) and a weekday service.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

FIXTURE_LAT = 28.60
STOP_LONS = (77.00, 77.01, 77.02, 77.03)

DEFAULT_FILES: dict[str, str] = {
    "agency.txt": (
        "agency_id,agency_name,agency_url,agency_timezone,agency_lang\n"
        "DMRC,Delhi Metro Rail Corporation,https://www.delhimetrorail.com,Asia/Kolkata,en\n"
    ),
    "routes.txt": (
        "route_id,agency_id,route_short_name,route_long_name,route_type,route_color\n"
        "R1,DMRC,RED,Red Line,1,EE1C25\n"
    ),
    "stops.txt": (
        "stop_id,stop_code,stop_name,stop_lat,stop_lon,location_type,parent_station\n"
        "S1,RED01,Alpha,28.60,77.00,0,\n"
        "S2,RED02,Bravo,28.60,77.01,0,\n"
        "S3,RED03,Charlie,28.60,77.02,0,\n"
        "S4,RED04,Delta,28.60,77.03,0,\n"
    ),
    "calendar.txt": (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
        "start_date,end_date\n"
        "WK,1,1,1,1,1,1,1,20260101,20261231\n"
    ),
    "calendar_dates.txt": (
        "service_id,date,exception_type\n"
        "WK,20260815,2\n"
    ),
    "shapes.txt": (
        "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
        + "".join(
            f"SH1,28.60,{77.00 + i * 0.005:.3f},{i + 1}\n" for i in range(7)
        )
        + "".join(
            f"SH2,28.60,{77.03 - i * 0.005:.3f},{i + 1}\n" for i in range(7)
        )
    ),
    "trips.txt": (
        "trip_id,route_id,service_id,trip_headsign,direction_id,shape_id\n"
        "T1,R1,WK,Towards Delta,0,SH1\n"
        "T2,R1,WK,Towards Alpha,1,SH2\n"
    ),
    "stop_times.txt": (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        "T1,08:00:00,08:00:30,S1,1\n"
        "T1,08:03:00,08:03:30,S2,2\n"
        "T1,08:06:00,08:06:30,S3,3\n"
        "T1,08:09:00,08:09:00,S4,4\n"
        "T2,09:00:00,09:00:30,S4,1\n"
        "T2,09:03:00,09:03:30,S3,2\n"
        "T2,09:06:00,09:06:30,S2,3\n"
        "T2,09:09:00,09:09:00,S1,4\n"
    ),
}


def write_gtfs_zip(
    path: Path,
    overrides: dict[str, str] | None = None,
    drop: tuple[str, ...] = (),
) -> Path:
    """Write the fixture GTFS ZIP, optionally overriding or dropping files."""
    files = {**DEFAULT_FILES, **(overrides or {})}
    for filename in drop:
        files.pop(filename, None)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)
    return path
