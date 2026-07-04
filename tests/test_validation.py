"""Tests for static GTFS dataset validation."""

from __future__ import annotations

from pathlib import Path

from gtfs_fixture import write_gtfs_zip
from metropulse.application.static_loader import read_gtfs_zip
from metropulse.application.validation import Severity, validate_dataset


def _valid_dataset(tmp_path: Path) -> dict[str, list[dict[str, str]]]:
    return read_gtfs_zip(write_gtfs_zip(tmp_path / "gtfs.zip"))


def test_fixture_dataset_is_valid(tmp_path: Path) -> None:
    report = validate_dataset(_valid_dataset(tmp_path))
    assert not report.has_errors
    assert report.warnings == []


def test_missing_required_file_is_error(tmp_path: Path) -> None:
    dataset = _valid_dataset(tmp_path)
    del dataset["stops.txt"]
    report = validate_dataset(dataset)
    assert any("stops.txt" in i.file and "missing" in i.message for i in report.errors)


def test_missing_shapes_is_only_warning(tmp_path: Path) -> None:
    dataset = _valid_dataset(tmp_path)
    del dataset["shapes.txt"]
    report = validate_dataset(dataset)
    assert not report.has_errors
    assert any(i.file == "shapes.txt" for i in report.warnings)


def test_missing_both_calendars_is_error(tmp_path: Path) -> None:
    dataset = _valid_dataset(tmp_path)
    del dataset["calendar.txt"]
    del dataset["calendar_dates.txt"]
    report = validate_dataset(dataset)
    assert any("calendar" in i.message for i in report.errors)


def test_missing_column_is_error(tmp_path: Path) -> None:
    dataset = _valid_dataset(tmp_path)
    dataset["routes.txt"] = [
        {k: v for k, v in row.items() if k != "route_type"} for row in dataset["routes.txt"]
    ]
    report = validate_dataset(dataset)
    assert any("route_type" in i.message for i in report.errors)


def test_bad_latitude_is_error(tmp_path: Path) -> None:
    dataset = _valid_dataset(tmp_path)
    dataset["stops.txt"][0]["stop_lat"] = "999"
    report = validate_dataset(dataset)
    assert any("stop_lat" in i.message for i in report.errors)


def test_unknown_stop_reference_is_error(tmp_path: Path) -> None:
    dataset = _valid_dataset(tmp_path)
    dataset["stop_times.txt"][0]["stop_id"] = "NOPE"
    report = validate_dataset(dataset)
    assert any("unknown stop_id 'NOPE'" in i.message for i in report.errors)


def test_unknown_route_reference_is_error(tmp_path: Path) -> None:
    dataset = _valid_dataset(tmp_path)
    dataset["trips.txt"][0]["route_id"] = "GHOST"
    report = validate_dataset(dataset)
    assert any("unknown route_id 'GHOST'" in i.message for i in report.errors)


def test_unknown_shape_reference_is_warning(tmp_path: Path) -> None:
    dataset = _valid_dataset(tmp_path)
    dataset["trips.txt"][0]["shape_id"] = "GHOST"
    report = validate_dataset(dataset)
    assert not report.has_errors
    assert any(
        "unknown shape_id 'GHOST'" in i.message and i.severity is Severity.WARNING
        for i in report.warnings
    )


def test_duplicate_stop_sequence_is_error(tmp_path: Path) -> None:
    dataset = _valid_dataset(tmp_path)
    dataset["stop_times.txt"][1]["stop_sequence"] = dataset["stop_times.txt"][0][
        "stop_sequence"
    ]
    report = validate_dataset(dataset)
    assert any("duplicate stop_sequence" in i.message for i in report.errors)


def test_departure_before_arrival_is_error(tmp_path: Path) -> None:
    dataset = _valid_dataset(tmp_path)
    dataset["stop_times.txt"][0]["arrival_time"] = "09:00:00"
    dataset["stop_times.txt"][0]["departure_time"] = "08:59:00"
    report = validate_dataset(dataset)
    assert any("departure_time precedes arrival_time" in i.message for i in report.errors)


def test_calendar_day_flags_validated(tmp_path: Path) -> None:
    dataset = _valid_dataset(tmp_path)
    dataset["calendar.txt"][0]["monday"] = "yes"
    report = validate_dataset(dataset)
    assert any("'monday' must be 0 or 1" in i.message for i in report.errors)


def test_report_render_includes_location(tmp_path: Path) -> None:
    dataset = _valid_dataset(tmp_path)
    dataset["stops.txt"][2]["stop_lat"] = "bogus"
    report = validate_dataset(dataset)
    rendered = [i.render() for i in report.errors]
    assert any(line.startswith("[ERROR] stops.txt:4") for line in rendered)
