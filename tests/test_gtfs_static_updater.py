"""Tests for the optional DMRC static feed auto-update service.

``test_expired_calendar_end_date_is_loaded_as_is_with_warning`` is the single
most important test in this file: see
``data/raw_gtfs/OVERRIDE_NOTES.md`` and
``metropulse.application.gtfs_static_updater`` for why this service must
never silently patch a stale ``calendar.txt`` ``end_date``.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from gtfs_fixture import write_gtfs_zip
from metropulse.application.gtfs_static_updater import (
    REMOTE_ETAG_KIND,
    GtfsStaticUpdateService,
)
from metropulse.application.static_loader import GtfsStaticLoader
from metropulse.domain.entities import utcnow
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.commuter_models import DatasetVersion
from metropulse.infrastructure.db.commuter_repositories import DatasetVersionRepository
from metropulse.infrastructure.db.models import Calendar
from metropulse.infrastructure.gtfs_static.dmrc_client import StaticFeedResponse


class FakeDmrcClient:
    """Duck-typed stand-in for :class:`DmrcStaticFeedClient` -- no network."""

    def __init__(self, response: StaticFeedResponse) -> None:
        self.response = response
        self.calls = 0

    async def fetch(self) -> StaticFeedResponse:
        self.calls += 1
        return self.response


class ExplodingClient:
    """Simulates a transport-level failure for the *_safe wrapper test."""

    async def fetch(self) -> StaticFeedResponse:
        raise RuntimeError("network is on fire")


async def _seed_remote_etag(session_factory: SessionFactory, etag: str) -> None:
    async with session_factory() as session:
        async with session.begin():
            DatasetVersionRepository(session).add(
                DatasetVersion(
                    kind=REMOTE_ETAG_KIND, version="", checksum=etag, created_at=utcnow()
                )
            )


async def _remote_etag_rows(session_factory: SessionFactory) -> list[DatasetVersion]:
    async with session_factory() as session:
        result = await session.execute(
            select(DatasetVersion).where(DatasetVersion.kind == REMOTE_ETAG_KIND)
        )
        return list(result.scalars().all())


async def _calendar_row_count(session_factory: SessionFactory) -> int:
    async with session_factory() as session:
        result = await session.execute(select(Calendar))
        return len(result.scalars().all())


async def test_unchanged_etag_skips_reload_and_writes_nothing(
    session_factory: SessionFactory, gtfs_zip: Path
) -> None:
    await _seed_remote_etag(session_factory, "etag-1")
    client = FakeDmrcClient(
        StaticFeedResponse(content=gtfs_zip.read_bytes(), etag="etag-1", last_modified=None)
    )
    service = GtfsStaticUpdateService(
        client, GtfsStaticLoader(session_factory), session_factory  # type: ignore[arg-type]
    )

    result = await service.check_for_update()

    assert result is None
    assert client.calls == 1
    assert await _calendar_row_count(session_factory) == 0  # nothing was loaded
    assert len(await _remote_etag_rows(session_factory)) == 1  # no new row written


async def test_changed_etag_with_valid_data_loads_and_stores_new_etag(
    session_factory: SessionFactory, gtfs_zip: Path
) -> None:
    await _seed_remote_etag(session_factory, "etag-old")
    client = FakeDmrcClient(
        StaticFeedResponse(
            content=gtfs_zip.read_bytes(),
            etag="etag-new",
            last_modified="Wed, 10 Aug 2023 00:00:00 GMT",
        )
    )
    service = GtfsStaticUpdateService(
        client, GtfsStaticLoader(session_factory), session_factory  # type: ignore[arg-type]
    )

    result = await service.check_for_update()

    assert result is not None
    assert result.counts["calendar"] == 1
    rows = await _remote_etag_rows(session_factory)
    assert len(rows) == 2  # old row preserved, new row appended
    async with session_factory() as session:
        latest = await DatasetVersionRepository(session).latest(REMOTE_ETAG_KIND)
    assert latest is not None
    assert latest.checksum == "etag-new"
    assert latest.version == "Wed, 10 Aug 2023 00:00:00 GMT"


async def test_no_prior_record_is_treated_as_changed(
    session_factory: SessionFactory, gtfs_zip: Path
) -> None:
    client = FakeDmrcClient(
        StaticFeedResponse(content=gtfs_zip.read_bytes(), etag="etag-first", last_modified=None)
    )
    service = GtfsStaticUpdateService(
        client, GtfsStaticLoader(session_factory), session_factory  # type: ignore[arg-type]
    )

    result = await service.check_for_update()

    assert result is not None
    async with session_factory() as session:
        latest = await DatasetVersionRepository(session).latest(REMOTE_ETAG_KIND)
    assert latest is not None
    assert latest.checksum == "etag-first"


async def test_changed_etag_with_invalid_data_is_not_loaded_and_etag_not_stored(
    session_factory: SessionFactory, tmp_path: Path
) -> None:
    await _seed_remote_etag(session_factory, "etag-old")
    bad_zip = write_gtfs_zip(
        tmp_path / "bad.zip",
        overrides={
            "stop_times.txt": (
                "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                "T1,08:00:00,08:00:30,UNKNOWN,1\n"
            )
        },
    )
    client = FakeDmrcClient(
        StaticFeedResponse(content=bad_zip.read_bytes(), etag="etag-bad", last_modified=None)
    )
    service = GtfsStaticUpdateService(
        client, GtfsStaticLoader(session_factory), session_factory  # type: ignore[arg-type]
    )

    result = await service.check_for_update()

    assert result is None
    async with session_factory() as session:
        latest = await DatasetVersionRepository(session).latest(REMOTE_ETAG_KIND)
    assert latest is not None
    assert latest.checksum == "etag-old"  # the bad version's ETag was NOT stored
    assert await _calendar_row_count(session_factory) == 0  # DB left untouched


async def test_check_for_update_safe_swallows_exceptions(
    session_factory: SessionFactory,
) -> None:
    service = GtfsStaticUpdateService(
        ExplodingClient(),  # type: ignore[arg-type]
        GtfsStaticLoader(session_factory),
        session_factory,
    )

    result = await service.check_for_update_safe()

    assert result is None


async def test_expired_calendar_end_date_is_loaded_as_is_with_warning(
    session_factory: SessionFactory, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The critical safety test: see module docstring."""
    expired_zip = write_gtfs_zip(
        tmp_path / "expired.zip",
        overrides={
            "calendar.txt": (
                "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
                "start_date,end_date\n"
                "WK,1,1,1,1,1,1,1,20200101,20200601\n"
            )
        },
    )
    client = FakeDmrcClient(
        StaticFeedResponse(
            content=expired_zip.read_bytes(), etag="etag-expired", last_modified=None
        )
    )
    service = GtfsStaticUpdateService(
        client, GtfsStaticLoader(session_factory), session_factory  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.WARNING, logger="metropulse.application.gtfs_static_updater"):
        result = await service.check_for_update()

    # 1. The data WAS loaded -- validation has nothing to do with stale
    #    dates, and this service must not reject or "fix" it either.
    assert result is not None
    async with session_factory() as session:
        calendar = await session.get(Calendar, "WK")
    assert calendar is not None
    assert calendar.end_date == date(2020, 6, 1)  # loaded exactly as published

    # 2. A prominent warning was logged identifying the offending service_id.
    warning_messages = [
        r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
    ]
    assert any("WK" in msg and "end_date" in msg for msg in warning_messages)

    # 3. This is still a legitimately loaded dataset -- its ETag IS recorded
    #    (only genuine validation failures withhold the ETag).
    async with session_factory() as session:
        latest = await DatasetVersionRepository(session).latest(REMOTE_ETAG_KIND)
    assert latest is not None
    assert latest.checksum == "etag-expired"


async def test_non_expired_calendar_logs_no_warning(
    session_factory: SessionFactory, gtfs_zip: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = FakeDmrcClient(
        StaticFeedResponse(content=gtfs_zip.read_bytes(), etag="etag-ok", last_modified=None)
    )
    service = GtfsStaticUpdateService(
        client, GtfsStaticLoader(session_factory), session_factory  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.WARNING, logger="metropulse.application.gtfs_static_updater"):
        result = await service.check_for_update()

    assert result is not None
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
