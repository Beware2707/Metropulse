"""GTFS static ZIP loader: parse, validate, and populate PostgreSQL.

The load is transactional: either the whole dataset replaces the previous one
or nothing changes. DMRC's feed (a few hundred thousand stop_times) fits
comfortably in memory, so we parse fully before touching the database.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from metropulse.application.validation import (
    RawDataset,
    ValidationReport,
    validate_dataset,
)
from metropulse.domain.gtfs_time import parse_gtfs_date, parse_gtfs_time
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.models import (
    Agency,
    Calendar,
    CalendarDate,
    Route,
    ShapePoint,
    Stop,
    StopTime,
    Trip,
)
from metropulse.infrastructure.db.repositories import StaticLoadRepository

logger = logging.getLogger(__name__)

GTFS_FILES = (
    "agency.txt",
    "routes.txt",
    "trips.txt",
    "stops.txt",
    "stop_times.txt",
    "calendar.txt",
    "calendar_dates.txt",
    "shapes.txt",
)


@dataclass
class LoadResult:
    """Outcome of a static load: per-table row counts and the report."""

    counts: dict[str, int] = field(default_factory=dict)
    report: ValidationReport = field(default_factory=ValidationReport)

    def summary(self) -> str:
        """One-line human summary of what was loaded."""
        parts = ", ".join(f"{table}={count}" for table, count in sorted(self.counts.items()))
        return f"loaded {parts}; {len(self.report.warnings)} warning(s)"


def read_gtfs_zip(zip_path: Path) -> dict[str, list[dict[str, str]]]:
    """Read all known GTFS files from a ZIP into raw string rows.

    Handles UTF-8 BOMs and whitespace around header names. Unknown files in
    the archive are ignored.
    """
    dataset: dict[str, list[dict[str, str]]] = {}
    with zipfile.ZipFile(zip_path) as archive:
        names = {Path(n).name: n for n in archive.namelist()}
        for filename in GTFS_FILES:
            member = names.get(filename)
            if member is None:
                continue
            with archive.open(member) as handle:
                text = io.TextIOWrapper(handle, encoding="utf-8-sig", newline="")
                reader = csv.DictReader(text)
                if reader.fieldnames:
                    reader.fieldnames = [name.strip() for name in reader.fieldnames]
                dataset[filename] = [
                    {k: (v or "").strip() for k, v in row.items() if k is not None}
                    for row in reader
                ]
    return dataset


class GtfsStaticLoader:
    """Validates and loads a GTFS static ZIP into the relational store."""

    def __init__(self, session_factory: SessionFactory, batch_size: int = 5000) -> None:
        self._session_factory = session_factory
        self._batch_size = batch_size

    async def load(self, zip_path: Path) -> LoadResult:
        """Validate ``zip_path`` and replace the static tables with its data.

        Raises :class:`metropulse.domain.exceptions.GtfsValidationError` when
        validation finds blocking errors; the database is left untouched.
        """
        logger.info("reading GTFS static archive %s", zip_path)
        dataset = read_gtfs_zip(zip_path)
        report = validate_dataset(dataset)
        for warning in report.warnings:
            logger.warning("%s", warning.render())
        report.raise_for_errors()

        result = LoadResult(report=report)
        async with self._session_factory() as session:
            async with session.begin():
                repo = StaticLoadRepository(session, batch_size=self._batch_size)
                await repo.delete_all_static()
                inserts: list[tuple[type[Any], list[dict[str, Any]]]] = [
                    (Agency, _agency_rows(dataset)),
                    (Route, _route_rows(dataset)),
                    (Stop, _stop_rows(dataset)),
                    (Calendar, _calendar_rows(dataset)),
                    (CalendarDate, _calendar_date_rows(dataset)),
                    (ShapePoint, _shape_rows(dataset)),
                    (Trip, _trip_rows(dataset)),
                    (StopTime, _stop_time_rows(dataset)),
                ]
                for model, rows in inserts:
                    count = await repo.bulk_insert(model, rows)
                    result.counts[model.__tablename__] = count
                    logger.info("inserted %d rows into %s", count, model.__tablename__)
        logger.info("static load complete: %s", result.summary())
        return result

    async def validate_only(self, zip_path: Path) -> ValidationReport:
        """Run validation without touching the database."""
        return validate_dataset(read_gtfs_zip(zip_path))


def _optional(value: str) -> str | None:
    return value if value else None


def _optional_int(value: str) -> int | None:
    return int(value) if value else None


def _optional_float(value: str) -> float | None:
    return float(value) if value else None


def _agency_rows(dataset: RawDataset) -> list[dict[str, Any]]:
    return [
        {
            # agency_id is optional in GTFS when there is a single agency.
            "agency_id": row.get("agency_id", "").strip() or "default",
            "agency_name": row["agency_name"],
            "agency_url": row["agency_url"],
            "agency_timezone": row["agency_timezone"],
            "agency_lang": _optional(row.get("agency_lang", "")),
        }
        for row in dataset.get("agency.txt", ())
    ]


def _route_rows(dataset: RawDataset) -> list[dict[str, Any]]:
    agencies = dataset.get("agency.txt", ())
    default_agency = (
        (agencies[0].get("agency_id", "").strip() or "default") if agencies else None
    )
    return [
        {
            "route_id": row["route_id"],
            "agency_id": row.get("agency_id", "").strip() or default_agency,
            "route_short_name": _optional(row.get("route_short_name", "")),
            "route_long_name": _optional(row.get("route_long_name", "")),
            "route_type": int(row["route_type"]),
            "route_color": _optional(row.get("route_color", "")),
            "route_text_color": _optional(row.get("route_text_color", "")),
        }
        for row in dataset.get("routes.txt", ())
    ]


def _stop_rows(dataset: RawDataset) -> list[dict[str, Any]]:
    return [
        {
            "stop_id": row["stop_id"],
            "stop_code": _optional(row.get("stop_code", "")),
            "stop_name": row["stop_name"],
            "stop_lat": float(row["stop_lat"]),
            "stop_lon": float(row["stop_lon"]),
            "zone_id": _optional(row.get("zone_id", "")),
            "location_type": _optional_int(row.get("location_type", "")),
            "parent_station": _optional(row.get("parent_station", "")),
        }
        for row in dataset.get("stops.txt", ())
    ]


def _calendar_rows(dataset: RawDataset) -> list[dict[str, Any]]:
    return [
        {
            "service_id": row["service_id"],
            "monday": row["monday"] == "1",
            "tuesday": row["tuesday"] == "1",
            "wednesday": row["wednesday"] == "1",
            "thursday": row["thursday"] == "1",
            "friday": row["friday"] == "1",
            "saturday": row["saturday"] == "1",
            "sunday": row["sunday"] == "1",
            "start_date": parse_gtfs_date(row["start_date"]),
            "end_date": parse_gtfs_date(row["end_date"]),
        }
        for row in dataset.get("calendar.txt", ())
    ]


def _calendar_date_rows(dataset: RawDataset) -> list[dict[str, Any]]:
    return [
        {
            "service_id": row["service_id"],
            "date": parse_gtfs_date(row["date"]),
            "exception_type": int(row["exception_type"]),
        }
        for row in dataset.get("calendar_dates.txt", ())
    ]


def _shape_rows(dataset: RawDataset) -> list[dict[str, Any]]:
    return [
        {
            "shape_id": row["shape_id"],
            "shape_pt_sequence": int(row["shape_pt_sequence"]),
            "shape_pt_lat": float(row["shape_pt_lat"]),
            "shape_pt_lon": float(row["shape_pt_lon"]),
            "shape_dist_traveled": _optional_float(row.get("shape_dist_traveled", "")),
        }
        for row in dataset.get("shapes.txt", ())
    ]


def _trip_rows(dataset: RawDataset) -> list[dict[str, Any]]:
    return [
        {
            "trip_id": row["trip_id"],
            "route_id": row["route_id"],
            "service_id": row["service_id"],
            "trip_headsign": _optional(row.get("trip_headsign", "")),
            "direction_id": _optional_int(row.get("direction_id", "")),
            "shape_id": _optional(row.get("shape_id", "")),
        }
        for row in dataset.get("trips.txt", ())
    ]


def _stop_time_rows(dataset: RawDataset) -> list[dict[str, Any]]:
    return [
        {
            "trip_id": row["trip_id"],
            "stop_sequence": int(row["stop_sequence"]),
            "stop_id": row["stop_id"],
            "arrival_seconds": parse_gtfs_time(row["arrival_time"]),
            "departure_seconds": parse_gtfs_time(row["departure_time"]),
            "shape_dist_traveled": _optional_float(row.get("shape_dist_traveled", "")),
        }
        for row in dataset.get("stop_times.txt", ())
    ]
