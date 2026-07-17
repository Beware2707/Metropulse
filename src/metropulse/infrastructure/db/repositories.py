"""Repository classes over the GTFS static tables and realtime history.

Each repository takes an ``AsyncSession`` per call site convention: the caller
owns the session/transaction lifecycle; repositories only issue statements.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Sequence, cast

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from metropulse.domain.entities import VehiclePosition
from metropulse.infrastructure.db.models import (
    Agency,
    Calendar,
    CalendarDate,
    Route,
    ShapePoint,
    Stop,
    StopTime,
    Trip,
    VehiclePositionRecord,
)


class RouteRepository:
    """Read access to routes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> Sequence[Route]:
        """All routes ordered by route_id."""
        result = await self._session.execute(select(Route).order_by(Route.route_id))
        return result.scalars().all()

    async def get(self, route_id: str) -> Route | None:
        """One route by primary key, or None."""
        return await self._session.get(Route, route_id)


class StopRepository:
    """Read access to stops/stations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def set_stop_codes(self, code_by_stop_id: dict[str, str]) -> int:
        """Backfill ``stop_code`` from DMRC's official station registry.

        The DMRC GTFS ships stop_code empty, yet every other DMRC dataset
        (ridership, OD flows) is keyed by these codes — this write is what
        makes those datasets joinable. Returns rows updated. Caller owns the
        transaction.
        """
        updated = 0
        for stop_id, code in code_by_stop_id.items():
            result = await self._session.execute(
                update(Stop).where(Stop.stop_id == stop_id).values(stop_code=code)
            )
            updated += int(cast(CursorResult[Any], result).rowcount or 0)
        return updated

    async def list_all(self, *, limit: int | None = None, offset: int = 0) -> Sequence[Stop]:
        """Stops ordered by name, with optional pagination."""
        stmt = select(Stop).order_by(Stop.stop_name, Stop.stop_id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get(self, stop_id: str) -> Stop | None:
        """One stop by primary key, or None."""
        return await self._session.get(Stop, stop_id)

    async def routes_serving(self, stop_id: str) -> Sequence[Route]:
        """Distinct routes whose trips call at the given stop."""
        stmt = (
            select(Route)
            .join(Trip, Trip.route_id == Route.route_id)
            .join(StopTime, StopTime.trip_id == Trip.trip_id)
            .where(StopTime.stop_id == stop_id)
            .distinct()
            .order_by(Route.route_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()


class TripRepository:
    """Read access to trips and their ordered stop sequences."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, trip_id: str) -> Trip | None:
        """One trip by primary key, or None."""
        return await self._session.get(Trip, trip_id)

    async def stop_times_with_stops(self, trip_id: str) -> Sequence[tuple[StopTime, Stop]]:
        """(StopTime, Stop) pairs for a trip ordered by stop_sequence."""
        stmt = (
            select(StopTime, Stop)
            .join(Stop, Stop.stop_id == StopTime.stop_id)
            .where(StopTime.trip_id == trip_id)
            .order_by(StopTime.stop_sequence)
        )
        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def active_trip_ids_at(
        self, service_ids: Sequence[str], elapsed_seconds: int
    ) -> Sequence[str]:
        """Trip IDs currently underway: first departure <= now <= last arrival.

        ``elapsed_seconds`` is seconds since local midnight of the service
        date, matching GTFS's own past-midnight convention (a trip departing
        at 25:30:00 is still "today"). Used to estimate vehicle positions
        from the schedule when no realtime feed is available (see
        ``application/schedule_position_source.py``).
        """
        if not service_ids:
            return []
        bounds = (
            select(
                StopTime.trip_id.label("trip_id"),
                func.min(StopTime.departure_seconds).label("start"),
                func.max(StopTime.arrival_seconds).label("end"),
            )
            .join(Trip, Trip.trip_id == StopTime.trip_id)
            .where(Trip.service_id.in_(service_ids))
            .group_by(StopTime.trip_id)
            .subquery()
        )
        stmt = select(bounds.c.trip_id).where(
            bounds.c.start <= elapsed_seconds, bounds.c.end >= elapsed_seconds
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()


class ShapeRepository:
    """Read access to shape polylines."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def points_for(self, shape_id: str) -> Sequence[ShapePoint]:
        """Shape points ordered by sequence."""
        stmt = (
            select(ShapePoint)
            .where(ShapePoint.shape_id == shape_id)
            .order_by(ShapePoint.shape_pt_sequence)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()


class StaticLoadRepository:
    """Bulk write access used exclusively by the static loader."""

    # Children before parents so FK constraints never block the wipe.
    _DELETE_ORDER = (StopTime, Trip, CalendarDate, Calendar, ShapePoint, Stop, Route, Agency)

    def __init__(self, session: AsyncSession, batch_size: int = 5000) -> None:
        self._session = session
        self._batch_size = batch_size

    async def delete_all_static(self) -> None:
        """Remove all static GTFS rows (history is untouched)."""
        for model in self._DELETE_ORDER:
            await self._session.execute(delete(model))

    async def bulk_insert(self, model: type[Any], rows: Sequence[dict[str, Any]]) -> int:
        """Insert rows in batches; returns the number inserted."""
        for start in range(0, len(rows), self._batch_size):
            batch = rows[start : start + self._batch_size]
            if batch:
                await self._session.execute(insert(model), batch)
        return len(rows)

    async def count(self, model: type[Any]) -> int:
        """Row count for a model (used for load verification)."""
        result = await self._session.execute(select(func.count()).select_from(model))
        return int(result.scalar_one())


class VehicleHistoryRepository:
    """Write/read access to the vehicle position history table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, positions: Iterable[VehiclePosition], recorded_at: datetime) -> int:
        """Persist a batch of positions; returns the number written."""
        rows = [
            {
                "vehicle_id": p.vehicle_id,
                "trip_id": p.trip_id,
                "route_id": p.route_id,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "bearing": p.bearing,
                "speed_mps": p.speed_mps,
                "feed_timestamp": p.timestamp,
                "recorded_at": recorded_at,
                "source": p.source,
            }
            for p in positions
        ]
        if rows:
            await self._session.execute(insert(VehiclePositionRecord), rows)
        return len(rows)

    async def recent_for_vehicle(
        self, vehicle_id: str, limit: int = 6
    ) -> Sequence[VehiclePositionRecord]:
        """Most recent history rows for one vehicle, newest first."""
        stmt = (
            select(VehiclePositionRecord)
            .where(VehiclePositionRecord.vehicle_id == vehicle_id)
            .order_by(VehiclePositionRecord.feed_timestamp.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def delete_older_than(self, cutoff: datetime) -> int:
        """Retention cleanup; returns the number of rows deleted."""
        result = await self._session.execute(
            delete(VehiclePositionRecord).where(VehiclePositionRecord.recorded_at < cutoff)
        )
        # AsyncSession.execute() is statically typed as returning the broader
        # Result[Any], but a DML statement (update/delete) always yields a
        # CursorResult at runtime, which does expose .rowcount.
        return int(cast(CursorResult[Any], result).rowcount or 0)
