"""Tests for repository classes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from factories import make_vehicle
from metropulse.infrastructure.db.base import SessionFactory
from metropulse.infrastructure.db.repositories import (
    RouteRepository,
    ShapeRepository,
    StopRepository,
    TripRepository,
    VehicleHistoryRepository,
)


async def test_route_repository(loaded_session_factory: SessionFactory) -> None:
    async with loaded_session_factory() as session:
        repo = RouteRepository(session)
        routes = await repo.list_all()
        assert [r.route_id for r in routes] == ["R1"]
        assert (await repo.get("R1")) is not None
        assert (await repo.get("NOPE")) is None


async def test_stop_repository_listing_and_pagination(
    loaded_session_factory: SessionFactory,
) -> None:
    async with loaded_session_factory() as session:
        repo = StopRepository(session)
        stops = await repo.list_all()
        assert [s.stop_name for s in stops] == ["Alpha", "Bravo", "Charlie", "Delta"]
        page = await repo.list_all(limit=2, offset=1)
        assert [s.stop_name for s in page] == ["Bravo", "Charlie"]


async def test_stop_repository_routes_serving(
    loaded_session_factory: SessionFactory,
) -> None:
    async with loaded_session_factory() as session:
        routes = await StopRepository(session).routes_serving("S2")
        assert [r.route_id for r in routes] == ["R1"]


async def test_trip_repository_ordered_stop_times(
    loaded_session_factory: SessionFactory,
) -> None:
    async with loaded_session_factory() as session:
        repo = TripRepository(session)
        pairs = await repo.stop_times_with_stops("T1")
        assert [stop.stop_id for _, stop in pairs] == ["S1", "S2", "S3", "S4"]
        assert [st.stop_sequence for st, _ in pairs] == [1, 2, 3, 4]


async def test_shape_repository_ordered_points(
    loaded_session_factory: SessionFactory,
) -> None:
    async with loaded_session_factory() as session:
        points = await ShapeRepository(session).points_for("SH1")
        assert len(points) == 7
        sequences = [p.shape_pt_sequence for p in points]
        assert sequences == sorted(sequences)


async def test_vehicle_history_roundtrip_and_retention(
    session_factory: SessionFactory,
) -> None:
    now = datetime.now(UTC)
    old = now - timedelta(hours=100)
    async with session_factory() as session:
        async with session.begin():
            repo = VehicleHistoryRepository(session)
            await repo.add_many(
                [make_vehicle(vehicle_id="v1", timestamp=old)], recorded_at=old
            )
            await repo.add_many(
                [make_vehicle(vehicle_id="v1", timestamp=now)], recorded_at=now
            )
    async with session_factory() as session:
        repo = VehicleHistoryRepository(session)
        recent = await repo.recent_for_vehicle("v1")
        assert len(recent) == 2
        assert recent[0].feed_timestamp >= recent[1].feed_timestamp
    async with session_factory() as session:
        async with session.begin():
            deleted = await VehicleHistoryRepository(session).delete_older_than(
                now - timedelta(hours=72)
            )
        assert deleted == 1
    async with session_factory() as session:
        remaining = await VehicleHistoryRepository(session).recent_for_vehicle("v1")
        assert len(remaining) == 1
