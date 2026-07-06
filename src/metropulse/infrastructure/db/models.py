"""SQLAlchemy ORM models for GTFS static data and vehicle position history.

Natural composite primary keys are used where GTFS defines them
(stop_times, shapes, calendar_dates); this avoids surrogate sequences and
gives the hot lookup paths a covering primary index for free.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# BigInteger PKs don't autoincrement on SQLite (used in tests); this variant
# keeps identity behaviour on both backends.
BigIntPk = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    """Declarative base for all MetroPulse tables."""


class Agency(Base):
    """GTFS agency.txt."""

    __tablename__ = "agencies"

    agency_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agency_name: Mapped[str] = mapped_column(String(255))
    agency_url: Mapped[str] = mapped_column(String(512))
    agency_timezone: Mapped[str] = mapped_column(String(64))
    agency_lang: Mapped[str | None] = mapped_column(String(16))


class Route(Base):
    """GTFS routes.txt."""

    __tablename__ = "routes"

    route_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agency_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("agencies.agency_id"), index=True
    )
    route_short_name: Mapped[str | None] = mapped_column(String(128))
    route_long_name: Mapped[str | None] = mapped_column(String(255))
    route_type: Mapped[int] = mapped_column(Integer)
    route_color: Mapped[str | None] = mapped_column(String(8))
    route_text_color: Mapped[str | None] = mapped_column(String(8))


class Stop(Base):
    """GTFS stops.txt."""

    __tablename__ = "stops"

    stop_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    stop_code: Mapped[str | None] = mapped_column(String(64))
    stop_name: Mapped[str] = mapped_column(String(255), index=True)
    stop_lat: Mapped[float] = mapped_column(Float)
    stop_lon: Mapped[float] = mapped_column(Float)
    zone_id: Mapped[str | None] = mapped_column(String(64))
    location_type: Mapped[int | None] = mapped_column(Integer)
    parent_station: Mapped[str | None] = mapped_column(String(64), index=True)


class Calendar(Base):
    """GTFS calendar.txt."""

    __tablename__ = "calendar"

    service_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    monday: Mapped[bool] = mapped_column(Boolean)
    tuesday: Mapped[bool] = mapped_column(Boolean)
    wednesday: Mapped[bool] = mapped_column(Boolean)
    thursday: Mapped[bool] = mapped_column(Boolean)
    friday: Mapped[bool] = mapped_column(Boolean)
    saturday: Mapped[bool] = mapped_column(Boolean)
    sunday: Mapped[bool] = mapped_column(Boolean)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)


class CalendarDate(Base):
    """GTFS calendar_dates.txt (service exceptions)."""

    __tablename__ = "calendar_dates"

    service_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    exception_type: Mapped[int] = mapped_column(Integer)


class Trip(Base):
    """GTFS trips.txt."""

    __tablename__ = "trips"

    trip_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    route_id: Mapped[str] = mapped_column(String(64), ForeignKey("routes.route_id"), index=True)
    service_id: Mapped[str] = mapped_column(String(64), index=True)
    trip_headsign: Mapped[str | None] = mapped_column(String(255))
    direction_id: Mapped[int | None] = mapped_column(Integer)
    shape_id: Mapped[str | None] = mapped_column(String(64), index=True)


class StopTime(Base):
    """GTFS stop_times.txt."""

    __tablename__ = "stop_times"

    trip_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("trips.trip_id"), primary_key=True
    )
    stop_sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    stop_id: Mapped[str] = mapped_column(String(64), ForeignKey("stops.stop_id"), index=True)
    arrival_seconds: Mapped[int] = mapped_column(Integer)
    departure_seconds: Mapped[int] = mapped_column(Integer)
    shape_dist_traveled: Mapped[float | None] = mapped_column(Float)


class ShapePoint(Base):
    """GTFS shapes.txt."""

    __tablename__ = "shape_points"

    shape_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    shape_pt_sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    shape_pt_lat: Mapped[float] = mapped_column(Float)
    shape_pt_lon: Mapped[float] = mapped_column(Float)
    shape_dist_traveled: Mapped[float | None] = mapped_column(Float)


class VehiclePositionRecord(Base):
    """Historical vehicle positions persisted every realtime poll."""

    __tablename__ = "vehicle_position_history"
    __table_args__ = (
        Index("ix_vph_vehicle_ts", "vehicle_id", "feed_timestamp"),
        Index("ix_vph_recorded_at", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[str] = mapped_column(String(64))
    trip_id: Mapped[str | None] = mapped_column(String(128))
    route_id: Mapped[str | None] = mapped_column(String(64))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    bearing: Mapped[float | None] = mapped_column(Float)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    feed_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # "realtime_gps" (an actual feed) or "schedule_estimate" (interpolated
    # from the static timetable) -- see domain.entities.VehiclePosition.
    source: Mapped[str] = mapped_column(String(32), server_default="realtime_gps")
