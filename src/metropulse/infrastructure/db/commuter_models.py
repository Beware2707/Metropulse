"""SQLAlchemy ORM models for commuter-facing features.

Two deliberate schema rules:

1. Columns referencing GTFS entities (stop_id, route_id, trip_id) are plain
   strings with NO foreign keys. Static GTFS reloads replace those tables
   wholesale inside a transaction; commuter data (favourites, exits,
   journeys) must survive a reload. Referential validity is enforced at
   write time in the application layer.

2. Prediction-adjacent tables (crowd_observations, analytics_events,
   journey_events) carry ``source``, ``confidence``, ``model_version`` and a
   JSON ``payload``. Future AI models write rows with source='model' — no
   schema migration required to introduce ML-based crowding or ETA models.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from metropulse.infrastructure.db.models import Base, BigIntPk

# JSONB on PostgreSQL (indexable), plain JSON elsewhere (SQLite in tests).
JsonB = JSON().with_variant(JSONB(), "postgresql")


class User(Base):
    """An anonymous device-scoped user account."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    platform: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FavouriteStation(Base):
    """A user's favourite station (Home, Work, ...)."""

    __tablename__ = "favourite_stations"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    stop_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str | None] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FavouriteRoute(Base):
    """A user's favourite route/line."""

    __tablename__ = "favourite_routes"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    route_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DestinationAlert(Base):
    """'Wake me when my train is N seconds from station X'."""

    __tablename__ = "destination_alerts"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    vehicle_id: Mapped[str] = mapped_column(String(64))
    target_stop_id: Mapped[str] = mapped_column(String(64))
    threshold_seconds: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), index=True)  # active|triggered|expired|cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonB)


class LastTrainReminder(Base):
    """'Remind me N minutes before the last train from station X'."""

    __tablename__ = "last_train_reminders"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    stop_id: Mapped[str] = mapped_column(String(64))
    route_id: Mapped[str | None] = mapped_column(String(64))
    direction_id: Mapped[int | None] = mapped_column(Integer)
    lead_minutes: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_notified_service_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LeaveHomeReminder(Base):
    """'Tell me when to leave to catch the HH:MM train from station X'.

    One-shot: notify_at = train departure - walking time - buffer, computed
    at creation so the worker's reminder pass is a single indexed range scan.
    """

    __tablename__ = "leave_home_reminders"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    stop_id: Mapped[str] = mapped_column(String(64))
    train_departure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    walking_minutes: Mapped[int] = mapped_column(Integer)
    buffer_minutes: Mapped[int] = mapped_column(Integer)
    notify_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16))  # pending|sent|cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PredictedDepartureNotice(Base):
    """Idempotency marker for proactive "time to leave" nudges.

    Unlike :class:`LeaveHomeReminder` (a one-shot reminder the user creates
    for a specific known train), this is written by
    ``ProactiveCommuteSchedulerService`` itself, once per user per service
    day, so the worker's periodic evaluation doesn't re-notify the same
    predicted commute on every pass within the lead window.
    """

    __tablename__ = "predicted_departure_notices"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_notified_service_date: Mapped[date | None] = mapped_column(Date)
    last_notified_departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ServiceAlert(Base):
    """A service disruption/advisory, admin-created or feed-ingested."""

    __tablename__ = "service_alerts"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(16))  # admin|feed
    severity: Mapped[str] = mapped_column(String(16))  # info|warning|severe
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    route_id: Mapped[str | None] = mapped_column(String(64), index=True)
    stop_id: Mapped[str | None] = mapped_column(String(64), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonB)


class Journey(Base):
    """A tracked trip from origin to destination station."""

    __tablename__ = "journeys"
    __table_args__ = (Index("ix_journeys_user_status", "user_id", "status"),)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE")
    )
    origin_stop_id: Mapped[str] = mapped_column(String(64))
    destination_stop_id: Mapped[str] = mapped_column(String(64))
    route_id: Mapped[str | None] = mapped_column(String(64))
    vehicle_id: Mapped[str | None] = mapped_column(String(64), index=True)
    trip_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))  # active|completed|abandoned
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonB)


class JourneyEvent(Base):
    """Append-only journey lifecycle events (also ML training data)."""

    __tablename__ = "journey_events"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    journey_id: Mapped[int] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonB)


class Notification(Base):
    """Per-user notification outbox (delivery channels are pluggable)."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StationExit(Base):
    """A physical station exit/gate with searchable landmarks."""

    __tablename__ = "station_exits"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    stop_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    landmarks: Mapped[list[str] | None] = mapped_column(JsonB)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonB)


class CoachExitHint(Base):
    """Which coach stops nearest to which exit at a station/direction."""

    __tablename__ = "coach_exit_hints"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    stop_id: Mapped[str] = mapped_column(String(64), index=True)
    route_id: Mapped[str | None] = mapped_column(String(64))
    direction_id: Mapped[int | None] = mapped_column(Integer)
    exit_id: Mapped[int] = mapped_column(
        ForeignKey("station_exits.id", ondelete="CASCADE")
    )
    coach_index: Mapped[int] = mapped_column(Integer)


class CrowdObservation(Base):
    """Crowding data points from any source: user reports, sensors, models.

    ``source`` + ``model_version`` + ``payload`` make this the single table
    both crowd-sourcing today and AI prediction later write into.
    """

    __tablename__ = "crowd_observations"
    __table_args__ = (
        Index("ix_crowd_route_dir_observed", "route_id", "direction_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    route_id: Mapped[str | None] = mapped_column(String(64))
    direction_id: Mapped[int | None] = mapped_column(Integer)
    stop_id: Mapped[str | None] = mapped_column(String(64))
    vehicle_id: Mapped[str | None] = mapped_column(String(64))
    coach_index: Mapped[int | None] = mapped_column(Integer)
    occupancy: Mapped[float] = mapped_column(Float)  # 0.0 (empty) .. 1.0 (crushed)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(16))  # user|sensor|model
    confidence: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonB)


class AnalyticsEvent(Base):
    """Raw product analytics events (append-only, retention-pruned)."""

    __tablename__ = "analytics_events"
    __table_args__ = (Index("ix_analytics_type_occurred", "event_type", "occurred_at"),)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Indexed: the retention job deletes by received_at range.
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonB)


class DatasetVersion(Base):
    """Versioned static datasets, driving offline bundle synchronisation."""

    __tablename__ = "dataset_versions"
    __table_args__ = (Index("ix_dataset_versions_kind_created", "kind", "created_at"),)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32))  # e.g. gtfs_static
    version: Mapped[str] = mapped_column(String(64))
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
