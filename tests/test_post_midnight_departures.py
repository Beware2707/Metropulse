"""Post-midnight departures: the trains that run after the date rolls over.

GTFS models a trip that runs past midnight as belonging to the day it
*started*, with an hours field that keeps counting past 24. The 00:45 train on
the 18th is stored under service date the 17th at ``24:45:00`` (88_500 s).

This is not a hypothetical corner of the spec -- the real DMRC feed in
``data/raw_gtfs/stop_times.txt`` has 1,410 stop_times departing at or after
24:00:00, the latest at 25:13. ``next_departure`` used to scan only today's and
tomorrow's service dates, so at 00:30 it skipped a train 15 minutes away and
reported tomorrow morning's first service instead -- wrong at the exact hour a
commuter on a platform most needs the answer.

The default fixture has no post-midnight trip, which is why the rest of the
suite never caught this. This one does.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from gtfs_fixture import DEFAULT_FILES, write_gtfs_zip

from metropulse.application.commuter.last_train import LastTrainService
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.application.static_loader import GtfsStaticLoader

IST = ZoneInfo("Asia/Kolkata")

# T3 is a late-night run that departs S2 at 24:45:00 -- i.e. 00:45 the NEXT
# calendar day -- while still belonging to its start day's service date.
_LATE_NIGHT_OVERRIDES = {
    "trips.txt": DEFAULT_FILES["trips.txt"] + "T3,R1,WK,Towards Delta,0,SH1\n",
    "stop_times.txt": (
        DEFAULT_FILES["stop_times.txt"]
        + "T3,24:42:00,24:42:30,S1,1\n"
        + "T3,24:45:00,24:45:30,S2,2\n"
        + "T3,24:48:00,24:48:30,S3,3\n"
        + "T3,24:51:00,24:51:00,S4,4\n"
    ),
}


@pytest.fixture
def last_train() -> LastTrainService:
    return LastTrainService(timezone="Asia/Kolkata")


@pytest.fixture
async def late_night_session_factory(
    session_factory: SessionFactory, tmp_path: Path
) -> SessionFactory:
    zip_path = write_gtfs_zip(tmp_path / "late.zip", overrides=_LATE_NIGHT_OVERRIDES)
    await GtfsStaticLoader(session_factory).load(zip_path)
    return session_factory


async def test_next_departure_finds_a_train_stored_on_yesterdays_service_date(
    late_night_session_factory: SessionFactory, last_train: LastTrainService
) -> None:
    """At 00:30 on the 7th, the 00:45 train (stored as the 6th @ 24:45) is next."""
    async with late_night_session_factory() as session:
        after = datetime(2026, 7, 7, 0, 30, 0, tzinfo=IST)
        info = await last_train.next_departure(session, "S2", after=after)

        assert info is not None, (
            "A train departs 15 minutes from now; reporting no next departure "
            "is the failure this test exists to prevent."
        )
        assert info.trip_id == "T3"
        # It belongs to the PREVIOUS service date...
        assert info.service_date == date(2026, 7, 6)
        # ...but departs on the 7th, in real wall-clock terms.
        assert info.departure_at == datetime(2026, 7, 7, 0, 45, 30, tzinfo=IST)
        assert info.departure_seconds == 24 * 3600 + 45 * 60 + 30


async def test_next_departure_prefers_the_earliest_across_service_dates(
    late_night_session_factory: SessionFactory, last_train: LastTrainService
) -> None:
    """Yesterday's 00:45 beats today's 08:03 -- ordering is by real time."""
    async with late_night_session_factory() as session:
        after = datetime(2026, 7, 7, 0, 0, 0, tzinfo=IST)
        info = await last_train.next_departure(session, "S2", after=after)
        assert info is not None
        assert info.trip_id == "T3"
        assert info.departure_at < datetime(2026, 7, 7, 8, 0, 0, tzinfo=IST)


async def test_next_departure_after_the_last_late_train_rolls_forward(
    late_night_session_factory: SessionFactory, last_train: LastTrainService
) -> None:
    """Once the 00:45 has gone, the answer is the morning service, not None."""
    async with late_night_session_factory() as session:
        after = datetime(2026, 7, 7, 1, 0, 0, tzinfo=IST)
        info = await last_train.next_departure(session, "S2", after=after)
        assert info is not None
        assert info.trip_id == "T1"
        assert info.departure_at == datetime(2026, 7, 7, 8, 3, 30, tzinfo=IST)


async def test_daytime_lookup_is_unaffected_by_the_yesterday_scan(
    late_night_session_factory: SessionFactory, last_train: LastTrainService
) -> None:
    """Scanning yesterday must not drag a stale departure into a daytime query."""
    async with late_night_session_factory() as session:
        after = datetime(2026, 7, 7, 7, 30, 0, tzinfo=IST)
        info = await last_train.next_departure(session, "S2", after=after)
        assert info is not None
        assert info.trip_id == "T1"
        assert info.departure_at == datetime(2026, 7, 7, 8, 3, 30, tzinfo=IST)
