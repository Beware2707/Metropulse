"""Tests for the GTFS static loader."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from gtfs_fixture import write_gtfs_zip
from metropulse.application.static_loader import GtfsStaticLoader
from metropulse.domain.exceptions import GtfsValidationError
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.models import Route, Stop, StopTime, Trip


async def test_loads_fixture_dataset(
    session_factory: SessionFactory, gtfs_zip: Path
) -> None:
    result = await GtfsStaticLoader(session_factory).load(gtfs_zip)
    assert result.counts == {
        "agencies": 1,
        "routes": 1,
        "stops": 4,
        "calendar": 1,
        "calendar_dates": 1,
        "shape_points": 14,
        "trips": 2,
        "stop_times": 8,
    }
    assert "loaded" in result.summary()


async def test_load_converts_types(
    session_factory: SessionFactory, gtfs_zip: Path
) -> None:
    await GtfsStaticLoader(session_factory).load(gtfs_zip)
    async with session_factory() as session:
        stop_time = (
            await session.execute(
                select(StopTime).where(
                    StopTime.trip_id == "T1", StopTime.stop_sequence == 2
                )
            )
        ).scalar_one()
        assert stop_time.arrival_seconds == 8 * 3600 + 3 * 60
        stop = await session.get(Stop, "S2")
        assert stop is not None
        assert stop.stop_lat == pytest.approx(28.60)
        trip = await session.get(Trip, "T1")
        assert trip is not None
        assert trip.direction_id == 0
        assert trip.shape_id == "SH1"


async def test_reload_replaces_previous_data(
    session_factory: SessionFactory, gtfs_zip: Path
) -> None:
    loader = GtfsStaticLoader(session_factory)
    await loader.load(gtfs_zip)
    await loader.load(gtfs_zip)
    async with session_factory() as session:
        count = (
            await session.execute(select(func.count()).select_from(Route))
        ).scalar_one()
        assert count == 1


async def test_invalid_dataset_raises_and_leaves_db_empty(
    session_factory: SessionFactory, tmp_path: Path
) -> None:
    bad_zip = write_gtfs_zip(
        tmp_path / "bad.zip",
        overrides={
            "stop_times.txt": (
                "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                "T1,08:00:00,08:00:30,UNKNOWN,1\n"
            )
        },
    )
    with pytest.raises(GtfsValidationError) as exc_info:
        await GtfsStaticLoader(session_factory).load(bad_zip)
    assert any("UNKNOWN" in line for line in exc_info.value.errors)
    async with session_factory() as session:
        count = (
            await session.execute(select(func.count()).select_from(Route))
        ).scalar_one()
        assert count == 0


async def test_validate_only_reports_without_loading(
    session_factory: SessionFactory, gtfs_zip: Path
) -> None:
    report = await GtfsStaticLoader(session_factory).validate_only(gtfs_zip)
    assert not report.has_errors
    async with session_factory() as session:
        count = (
            await session.execute(select(func.count()).select_from(Route))
        ).scalar_one()
        assert count == 0


async def test_load_without_shapes_succeeds(
    session_factory: SessionFactory, tmp_path: Path
) -> None:
    zip_path = write_gtfs_zip(tmp_path / "noshapes.zip", drop=("shapes.txt",))
    result = await GtfsStaticLoader(session_factory).load(zip_path)
    assert result.counts["shape_points"] == 0
    assert any(w.file == "shapes.txt" for w in result.report.warnings)
