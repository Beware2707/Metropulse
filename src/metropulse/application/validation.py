"""Validation of a parsed static GTFS dataset.

Validation runs on the raw string rows before any type conversion so that a
single bad row produces a precise report line instead of a stack trace deep in
the loader.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Mapping, Sequence

from metropulse.domain.exceptions import GtfsValidationError
from metropulse.domain.gtfs_time import parse_gtfs_date, parse_gtfs_time

RawRows = Sequence[Mapping[str, str]]
RawDataset = Mapping[str, RawRows]

REQUIRED_FILES: dict[str, tuple[str, ...]] = {
    "agency.txt": ("agency_name", "agency_url", "agency_timezone"),
    "routes.txt": ("route_id", "route_type"),
    "trips.txt": ("trip_id", "route_id", "service_id"),
    "stops.txt": ("stop_id", "stop_name", "stop_lat", "stop_lon"),
    "stop_times.txt": ("trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"),
}
CONDITIONAL_FILES: dict[str, tuple[str, ...]] = {
    "calendar.txt": (
        "service_id",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "start_date",
        "end_date",
    ),
    "calendar_dates.txt": ("service_id", "date", "exception_type"),
    "shapes.txt": ("shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"),
}


class Severity(StrEnum):
    """Issue severity: errors block loading, warnings do not."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A single problem found in the dataset."""

    file: str
    row: int | None
    message: str
    severity: Severity

    def render(self) -> str:
        """Human-readable one-line description."""
        location = f"{self.file}:{self.row}" if self.row is not None else self.file
        return f"[{self.severity.value.upper()}] {location}: {self.message}"


@dataclass
class ValidationReport:
    """Aggregated validation result for a dataset."""

    issues: list[ValidationIssue] = field(default_factory=list)

    def add(
        self, file: str, message: str, *, row: int | None = None,
        severity: Severity = Severity.ERROR,
    ) -> None:
        """Record an issue."""
        self.issues.append(ValidationIssue(file, row, message, severity))

    @property
    def errors(self) -> list[ValidationIssue]:
        """Blocking issues only."""
        return [i for i in self.issues if i.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Non-blocking issues only."""
        return [i for i in self.issues if i.severity is Severity.WARNING]

    @property
    def has_errors(self) -> bool:
        """Whether any blocking issue was found."""
        return bool(self.errors)

    def raise_for_errors(self) -> None:
        """Raise :class:`GtfsValidationError` if any blocking issue exists."""
        if self.has_errors:
            raise GtfsValidationError([i.render() for i in self.errors])


def validate_dataset(dataset: RawDataset) -> ValidationReport:
    """Validate structure, field formats and cross-file references.

    Returns a report; the caller decides whether warnings are acceptable.
    """
    report = ValidationReport()
    _check_presence(dataset, report)
    for filename, columns in {**REQUIRED_FILES, **CONDITIONAL_FILES}.items():
        if filename in dataset:
            _check_columns(filename, columns, dataset[filename], report)
    _check_agency(dataset.get("agency.txt", ()), report)
    route_ids = _check_routes(dataset.get("routes.txt", ()), report)
    stop_ids = _check_stops(dataset.get("stops.txt", ()), report)
    service_ids = _check_calendar(
        dataset.get("calendar.txt", ()), dataset.get("calendar_dates.txt", ()), report
    )
    shape_ids = _check_shapes(dataset.get("shapes.txt", ()), report)
    trip_ids = _check_trips(
        dataset.get("trips.txt", ()), route_ids, service_ids, shape_ids, report
    )
    _check_stop_times(dataset.get("stop_times.txt", ()), trip_ids, stop_ids, report)
    return report


def _check_presence(dataset: RawDataset, report: ValidationReport) -> None:
    for filename in REQUIRED_FILES:
        if filename not in dataset:
            report.add(filename, "required file is missing")
    if "calendar.txt" not in dataset and "calendar_dates.txt" not in dataset:
        report.add("calendar.txt", "either calendar.txt or calendar_dates.txt is required")
    if "shapes.txt" not in dataset:
        report.add("shapes.txt", "file missing; shape-based ETA will be degraded",
                   severity=Severity.WARNING)


def _check_columns(
    filename: str, required: tuple[str, ...], rows: RawRows, report: ValidationReport
) -> None:
    if not rows:
        report.add(filename, "file is empty")
        return
    present = set(rows[0].keys())
    for column in required:
        if column not in present:
            report.add(filename, f"missing required column '{column}'")


def _has_columns(rows: RawRows, columns: tuple[str, ...]) -> bool:
    return bool(rows) and all(c in rows[0] for c in columns)


def _check_agency(rows: RawRows, report: ValidationReport) -> None:
    if not _has_columns(rows, REQUIRED_FILES["agency.txt"]):
        return
    for i, row in enumerate(rows, start=2):
        for column in ("agency_name", "agency_url", "agency_timezone"):
            if not row.get(column, "").strip():
                report.add("agency.txt", f"empty '{column}'", row=i)


def _check_routes(rows: RawRows, report: ValidationReport) -> set[str]:
    ids: set[str] = set()
    if not _has_columns(rows, REQUIRED_FILES["routes.txt"]):
        return ids
    for i, row in enumerate(rows, start=2):
        route_id = row.get("route_id", "").strip()
        if not route_id:
            report.add("routes.txt", "empty route_id", row=i)
            continue
        if route_id in ids:
            report.add("routes.txt", f"duplicate route_id '{route_id}'", row=i)
        ids.add(route_id)
        if not _is_int(row.get("route_type", "")):
            report.add("routes.txt", f"non-integer route_type '{row.get('route_type')}'", row=i)
    return ids


def _check_stops(rows: RawRows, report: ValidationReport) -> set[str]:
    ids: set[str] = set()
    if not _has_columns(rows, REQUIRED_FILES["stops.txt"]):
        return ids
    for i, row in enumerate(rows, start=2):
        stop_id = row.get("stop_id", "").strip()
        if not stop_id:
            report.add("stops.txt", "empty stop_id", row=i)
            continue
        if stop_id in ids:
            report.add("stops.txt", f"duplicate stop_id '{stop_id}'", row=i)
        ids.add(stop_id)
        lat, lon = _as_float(row.get("stop_lat", "")), _as_float(row.get("stop_lon", ""))
        if lat is None or not -90.0 <= lat <= 90.0:
            report.add("stops.txt", f"invalid stop_lat '{row.get('stop_lat')}'", row=i)
        if lon is None or not -180.0 <= lon <= 180.0:
            report.add("stops.txt", f"invalid stop_lon '{row.get('stop_lon')}'", row=i)
    return ids


def _check_calendar(
    calendar_rows: RawRows, calendar_date_rows: RawRows, report: ValidationReport
) -> set[str]:
    service_ids: set[str] = set()
    if _has_columns(calendar_rows, CONDITIONAL_FILES["calendar.txt"]):
        for i, row in enumerate(calendar_rows, start=2):
            service_id = row.get("service_id", "").strip()
            if not service_id:
                report.add("calendar.txt", "empty service_id", row=i)
                continue
            service_ids.add(service_id)
            for day in ("monday", "tuesday", "wednesday", "thursday",
                        "friday", "saturday", "sunday"):
                if row.get(day, "").strip() not in ("0", "1"):
                    report.add("calendar.txt", f"'{day}' must be 0 or 1", row=i)
            start = _as_date(row.get("start_date", ""))
            end = _as_date(row.get("end_date", ""))
            if start is None:
                report.add("calendar.txt", f"invalid start_date '{row.get('start_date')}'", row=i)
            if end is None:
                report.add("calendar.txt", f"invalid end_date '{row.get('end_date')}'", row=i)
            if start is not None and end is not None and end < start:
                report.add("calendar.txt", "end_date precedes start_date", row=i)
    if _has_columns(calendar_date_rows, CONDITIONAL_FILES["calendar_dates.txt"]):
        for i, row in enumerate(calendar_date_rows, start=2):
            service_id = row.get("service_id", "").strip()
            if not service_id:
                report.add("calendar_dates.txt", "empty service_id", row=i)
                continue
            service_ids.add(service_id)
            if _as_date(row.get("date", "")) is None:
                report.add("calendar_dates.txt", f"invalid date '{row.get('date')}'", row=i)
            if row.get("exception_type", "").strip() not in ("1", "2"):
                report.add("calendar_dates.txt", "exception_type must be 1 or 2", row=i)
    return service_ids


def _check_shapes(rows: RawRows, report: ValidationReport) -> set[str]:
    ids: set[str] = set()
    if not _has_columns(rows, CONDITIONAL_FILES["shapes.txt"]):
        return ids
    for i, row in enumerate(rows, start=2):
        shape_id = row.get("shape_id", "").strip()
        if not shape_id:
            report.add("shapes.txt", "empty shape_id", row=i)
            continue
        ids.add(shape_id)
        if _as_float(row.get("shape_pt_lat", "")) is None:
            report.add("shapes.txt", f"invalid shape_pt_lat '{row.get('shape_pt_lat')}'", row=i)
        if _as_float(row.get("shape_pt_lon", "")) is None:
            report.add("shapes.txt", f"invalid shape_pt_lon '{row.get('shape_pt_lon')}'", row=i)
        if not _is_int(row.get("shape_pt_sequence", "")):
            report.add("shapes.txt", "non-integer shape_pt_sequence", row=i)
    return ids


def _check_trips(
    rows: RawRows,
    route_ids: set[str],
    service_ids: set[str],
    shape_ids: set[str],
    report: ValidationReport,
) -> set[str]:
    ids: set[str] = set()
    if not _has_columns(rows, REQUIRED_FILES["trips.txt"]):
        return ids
    for i, row in enumerate(rows, start=2):
        trip_id = row.get("trip_id", "").strip()
        if not trip_id:
            report.add("trips.txt", "empty trip_id", row=i)
            continue
        if trip_id in ids:
            report.add("trips.txt", f"duplicate trip_id '{trip_id}'", row=i)
        ids.add(trip_id)
        if row.get("route_id", "").strip() not in route_ids:
            report.add("trips.txt", f"unknown route_id '{row.get('route_id')}'", row=i)
        if service_ids and row.get("service_id", "").strip() not in service_ids:
            report.add("trips.txt", f"unknown service_id '{row.get('service_id')}'", row=i)
        shape_id = row.get("shape_id", "").strip()
        if shape_id and shape_ids and shape_id not in shape_ids:
            report.add("trips.txt", f"unknown shape_id '{shape_id}'", row=i,
                       severity=Severity.WARNING)
    return ids


def _check_stop_times(
    rows: RawRows, trip_ids: set[str], stop_ids: set[str], report: ValidationReport
) -> None:
    if not _has_columns(rows, REQUIRED_FILES["stop_times.txt"]):
        return
    seen: set[tuple[str, str]] = set()
    for i, row in enumerate(rows, start=2):
        trip_id = row.get("trip_id", "").strip()
        if trip_id not in trip_ids:
            report.add("stop_times.txt", f"unknown trip_id '{trip_id}'", row=i)
        if row.get("stop_id", "").strip() not in stop_ids:
            report.add("stop_times.txt", f"unknown stop_id '{row.get('stop_id')}'", row=i)
        sequence = row.get("stop_sequence", "").strip()
        if not _is_int(sequence):
            report.add("stop_times.txt", f"non-integer stop_sequence '{sequence}'", row=i)
        elif (trip_id, sequence) in seen:
            report.add("stop_times.txt",
                       f"duplicate stop_sequence {sequence} for trip '{trip_id}'", row=i)
        else:
            seen.add((trip_id, sequence))
        arrival = _as_time(row.get("arrival_time", ""))
        departure = _as_time(row.get("departure_time", ""))
        if arrival is None:
            report.add("stop_times.txt", f"invalid arrival_time '{row.get('arrival_time')}'",
                       row=i)
        if departure is None:
            report.add("stop_times.txt",
                       f"invalid departure_time '{row.get('departure_time')}'", row=i)
        if arrival is not None and departure is not None and departure < arrival:
            report.add("stop_times.txt", "departure_time precedes arrival_time", row=i)


def _is_int(value: str) -> bool:
    try:
        int(value.strip())
    except (ValueError, AttributeError):
        return False
    return True


def _as_float(value: str) -> float | None:
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


def _as_date(value: str) -> date | None:
    try:
        return parse_gtfs_date(value)
    except ValueError:
        return None


def _as_time(value: str) -> int | None:
    try:
        return parse_gtfs_time(value)
    except ValueError:
        return None
