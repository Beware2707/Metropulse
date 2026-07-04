"""Commuter features: users, favourites, alerts, journeys, exits, analytics.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("platform", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_device_id", "users", ["device_id"], unique=True)
    op.create_index("ix_users_token_hash", "users", ["token_hash"], unique=True)

    op.create_table(
        "favourite_stations",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("stop_id", sa.String(64), primary_key=True),
        sa.Column("label", sa.String(64), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "favourite_routes",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("route_id", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "destination_alerts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("vehicle_id", sa.String(64), nullable=False),
        sa.Column("target_stop_id", sa.String(64), nullable=False),
        sa.Column("threshold_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", _JSONB, nullable=True),
    )
    op.create_index("ix_destination_alerts_user_id", "destination_alerts", ["user_id"])
    op.create_index("ix_destination_alerts_status", "destination_alerts", ["status"])

    op.create_table(
        "last_train_reminders",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stop_id", sa.String(64), nullable=False),
        sa.Column("route_id", sa.String(64), nullable=True),
        sa.Column("direction_id", sa.Integer(), nullable=True),
        sa.Column("lead_minutes", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_notified_service_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_last_train_reminders_user_id", "last_train_reminders", ["user_id"])

    op.create_table(
        "service_alerts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("route_id", sa.String(64), nullable=True),
        sa.Column("stop_id", sa.String(64), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", _JSONB, nullable=True),
    )
    op.create_index("ix_service_alerts_route_id", "service_alerts", ["route_id"])
    op.create_index("ix_service_alerts_stop_id", "service_alerts", ["stop_id"])

    op.create_table(
        "journeys",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("origin_stop_id", sa.String(64), nullable=False),
        sa.Column("destination_stop_id", sa.String(64), nullable=False),
        sa.Column("route_id", sa.String(64), nullable=True),
        sa.Column("vehicle_id", sa.String(64), nullable=True),
        sa.Column("trip_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", _JSONB, nullable=True),
    )
    op.create_index("ix_journeys_user_status", "journeys", ["user_id", "status"])
    op.create_index("ix_journeys_vehicle_id", "journeys", ["vehicle_id"])

    op.create_table(
        "journey_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "journey_id", sa.BigInteger(),
            sa.ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", _JSONB, nullable=True),
    )
    op.create_index("ix_journey_events_journey_id", "journey_events", ["journey_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload", _JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])

    op.create_table(
        "station_exits",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("stop_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("landmarks", _JSONB, nullable=True),
        sa.Column("payload", _JSONB, nullable=True),
    )
    op.create_index("ix_station_exits_stop_id", "station_exits", ["stop_id"])

    op.create_table(
        "coach_exit_hints",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("stop_id", sa.String(64), nullable=False),
        sa.Column("route_id", sa.String(64), nullable=True),
        sa.Column("direction_id", sa.Integer(), nullable=True),
        sa.Column(
            "exit_id", sa.BigInteger(),
            sa.ForeignKey("station_exits.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("coach_index", sa.Integer(), nullable=False),
    )
    op.create_index("ix_coach_exit_hints_stop_id", "coach_exit_hints", ["stop_id"])

    op.create_table(
        "crowd_observations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("route_id", sa.String(64), nullable=True),
        sa.Column("direction_id", sa.Integer(), nullable=True),
        sa.Column("stop_id", sa.String(64), nullable=True),
        sa.Column("vehicle_id", sa.String(64), nullable=True),
        sa.Column("coach_index", sa.Integer(), nullable=True),
        sa.Column("occupancy", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("payload", _JSONB, nullable=True),
    )
    op.create_index("ix_crowd_observations_observed_at", "crowd_observations", ["observed_at"])
    op.create_index(
        "ix_crowd_route_dir_observed",
        "crowd_observations",
        ["route_id", "direction_id", "observed_at"],
    )

    op.create_table(
        "analytics_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", _JSONB, nullable=True),
    )
    op.create_index("ix_analytics_events_user_id", "analytics_events", ["user_id"])
    op.create_index(
        "ix_analytics_type_occurred", "analytics_events", ["event_type", "occurred_at"]
    )

    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_dataset_versions_kind_created", "dataset_versions", ["kind", "created_at"]
    )


def downgrade() -> None:
    for table in (
        "dataset_versions",
        "analytics_events",
        "crowd_observations",
        "coach_exit_hints",
        "station_exits",
        "notifications",
        "journey_events",
        "journeys",
        "service_alerts",
        "last_train_reminders",
        "destination_alerts",
        "favourite_routes",
        "favourite_stations",
        "users",
    ):
        op.drop_table(table)
