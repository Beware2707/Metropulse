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


class LlmDelayRefinement(Base):
    """Cached LLM-refined delay estimate for a route/hour/day-type bucket.

    Written only by ``LlmDelayRefinementScheduler`` on its periodic pass;
    read only by ``LlmEnhancedDelayEstimator`` to optionally nudge
    ``DelayPredictionService``'s own historical estimate within a bounded
    range (see ``application/intelligence/llm_delay_refiner.py``). Empty
    table — the natural state whenever no LLM provider key is configured —
    means every read is a cache miss and the historical estimate is used
    unchanged everywhere. Provider-agnostic: the same row shape holds a
    refinement regardless of whether Claude, OpenAI, or Gemini produced it.

    One row per (route_id, direction_id, hour_of_day, day_type) bucket,
    overwritten (not appended) on each refresh — ``direction_id`` can be
    NULL (today's delay model doesn't resolve direction), so this uses a
    surrogate primary key with a lookup index rather than a composite key
    that can't cleanly include a nullable column.
    """

    __tablename__ = "llm_delay_refinements"
    __table_args__ = (
        Index(
            "ix_llm_delay_refinements_bucket",
            "route_id", "direction_id", "hour_of_day", "day_type",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    route_id: Mapped[str] = mapped_column(String(64))
    direction_id: Mapped[int | None] = mapped_column(Integer)
    hour_of_day: Mapped[int] = mapped_column(Integer)
    day_type: Mapped[str] = mapped_column(String(16))  # weekday|weekend
    adjusted_delay_seconds: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


class SharedJourney(Base):
    """A public, token-addressed live view of a user's active journey.

    Privacy model: the ``token`` (a ``secrets.token_urlsafe`` string) is the
    *only* secret. The public read exposes journey facts (origin/destination
    names, last position, nearest station) and never the sharer's user id,
    device, or any other PII. A journey may be shared, stopped, and re-shared
    over time, so ``journey_id`` is indexed but not unique; the live share is
    the one whose ``expires_at`` is still in the future.
    """

    __tablename__ = "shared_journeys"
    __table_args__ = (Index("ix_shared_journeys_journey", "journey_id"),)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    journey_id: Mapped[int] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE")
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    last_lat: Mapped[float | None] = mapped_column(Float)
    last_lon: Mapped[float | None] = mapped_column(Float)
    position_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RiderReport(Base):
    """A community-sourced disruption report, deliberately distinct from the
    authoritative operator :class:`ServiceAlert` table.

    ``source`` is always 'rider' and ``verified`` is False -- these rows are
    unverified crowd signals, surfaced separately from operator alerts so the
    two are never conflated. ``user_id`` is retained for moderation/rate
    limiting only and is NEVER exposed on the public read (which returns the
    report facts deduped/counted by stop+category).
    """

    __tablename__ = "rider_reports"
    __table_args__ = (
        Index("ix_rider_reports_reported_at", "reported_at"),
        Index("ix_rider_reports_stop_category", "stop_id", "category", "reported_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    stop_id: Mapped[str | None] = mapped_column(String(64))
    route_id: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(280))
    category: Mapped[str] = mapped_column(String(16))  # delay|crowding|closure|other
    source: Mapped[str] = mapped_column(String(16))  # always 'rider'
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
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


class StationFacility(Base):
    """Station accessibility + parking facilities, curated from a Delhi
    Transport Stack dataset (dmrc_station_details_with_parking.xlsx) and
    matched to GTFS stops by normalized name / nearest-coordinate
    fallback -- see metropulse.application.commuter.station_facility_loader.

    Like station_exits, this is curated reference data, not live commuter
    data -- a re-run of the loader replaces the table wholesale in a
    transaction (see the module docstring's rule 1).
    """

    __tablename__ = "station_facilities"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    stop_id: Mapped[str] = mapped_column(String(64), index=True, unique=True)
    station_code: Mapped[str | None] = mapped_column(String(16))
    elevated: Mapped[bool | None] = mapped_column(Boolean)
    toilet: Mapped[bool | None] = mapped_column(Boolean)
    gate_location: Mapped[str | None] = mapped_column(Text)
    parking_lots: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    match_method: Mapped[str] = mapped_column(String(16))


class LastMileRoute(Base):
    """A shared-mobility (e-rickshaw) last-mile route anchored at a metro
    station, curated from a Delhi Transport Stack GTFS feed
    (shared_mobility_gtfs_v1.zip) and matched to GTFS stops by normalized
    name / nearest-coordinate fallback -- see
    metropulse.application.commuter.last_mile_loader.

    Curated reference data in its OWN table, deliberately separate from
    the core GTFS static tables (which get wholesale-replaced whenever
    DMRC's feed reloads -- see the module docstring's rule 1). A re-run
    of this loader replaces only this table wholesale in a transaction.
    """

    __tablename__ = "last_mile_routes"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    route_id: Mapped[str] = mapped_column(String(64), index=True, unique=True)
    hub_stop_id: Mapped[str] = mapped_column(String(64), index=True)
    hub_match_method: Mapped[str] = mapped_column(String(16))
    route_short_name: Mapped[str | None] = mapped_column(String(128))
    route_long_name: Mapped[str | None] = mapped_column(String(255))
    start_time: Mapped[str | None] = mapped_column(String(8))
    end_time: Mapped[str | None] = mapped_column(String(8))
    headway_secs: Mapped[int | None] = mapped_column(Integer)
    stops: Mapped[list[dict[str, Any]]] = mapped_column(JsonB)


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


class StationAccessibility(Base):
    """The step-free path graph inside a station: gates, lifts, platforms and
    the walk/elevator edges between them, from DMRC's GTFS-Pathways dataset
    (Open Transit Data portal).

    Coverage is partial by source: the dataset spans the Red, Yellow and Pink
    lines and marks some stations incomplete. ``complete`` is True only when
    the station has at least one full gate->lift->platform chain — the app must
    say "no accessibility data" for absent stations, never guess. Curated
    reference data: the loader replaces the table wholesale.
    """

    __tablename__ = "station_accessibility"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    stop_id: Mapped[str] = mapped_column(String(64), index=True, unique=True)
    station_code: Mapped[str | None] = mapped_column(String(16))
    gates: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    lifts: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    platforms: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    edges: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
    match_method: Mapped[str] = mapped_column(String(16))


class StationHourlyLoad(Base):
    """Typical hourly entries/exits for a station, averaged from DMRC's
    station-wise ridership dataset (Open Transit Data portal).

    ``period`` records the data's vintage (e.g. 'september_2024') and MUST be
    surfaced wherever this is shown — "typically busy" from a dated snapshot
    is honest only with the date attached. ``profiles`` maps day_kind
    (weekday|saturday|sunday) to 24-element entry/exit arrays whose index 0 is
    04:00 of the service day (DMRC's HR4..HR27 convention, wrapping past
    midnight). Curated reference data: wholesale replace on load.
    """

    __tablename__ = "station_hourly_load"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    stop_id: Mapped[str] = mapped_column(String(64), index=True, unique=True)
    station_code: Mapped[str | None] = mapped_column(String(16))
    period: Mapped[str] = mapped_column(String(32))
    profiles: Mapped[dict[str, Any]] = mapped_column(JsonB)
    match_method: Mapped[str] = mapped_column(String(16))


class StationTopDestinations(Base):
    """Where riders from this origin actually go, from DMRC's monthly
    origin-destination flow matrix (Open Transit Data portal).

    ``top`` is a ranked list of {dest_stop_id, dest_name, count} for the month
    named in ``period``; ``total_out`` is the origin's total outbound riders
    that month. Counts are real measured ridership, not estimates — attribute
    them as "DMRC OD data, <period>". Curated reference data: wholesale
    replace on load.
    """

    __tablename__ = "station_top_destinations"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    stop_id: Mapped[str] = mapped_column(String(64), index=True, unique=True)
    station_code: Mapped[str | None] = mapped_column(String(16))
    period: Mapped[str] = mapped_column(String(32))
    total_out: Mapped[int] = mapped_column(Integer)
    top: Mapped[list[dict[str, Any]]] = mapped_column(JsonB)
    match_method: Mapped[str] = mapped_column(String(16))


class Feedback(Base):
    """A user-submitted feedback message (Sprint 4: beta launch)."""

    __tablename__ = "feedback"
    __table_args__ = (Index("ix_feedback_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str | None] = mapped_column(String(16))  # bug|suggestion|praise|other
    message: Mapped[str] = mapped_column(Text)
    app_version: Mapped[str | None] = mapped_column(String(32))
    platform: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
