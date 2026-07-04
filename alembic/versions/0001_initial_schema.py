"""Initial schema: GTFS static tables and vehicle position history.

Revision ID: 0001
Revises:
Create Date: 2026-07-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agencies",
        sa.Column("agency_id", sa.String(64), primary_key=True),
        sa.Column("agency_name", sa.String(255), nullable=False),
        sa.Column("agency_url", sa.String(512), nullable=False),
        sa.Column("agency_timezone", sa.String(64), nullable=False),
        sa.Column("agency_lang", sa.String(16), nullable=True),
    )
    op.create_table(
        "routes",
        sa.Column("route_id", sa.String(64), primary_key=True),
        sa.Column(
            "agency_id", sa.String(64), sa.ForeignKey("agencies.agency_id"), nullable=True
        ),
        sa.Column("route_short_name", sa.String(128), nullable=True),
        sa.Column("route_long_name", sa.String(255), nullable=True),
        sa.Column("route_type", sa.Integer(), nullable=False),
        sa.Column("route_color", sa.String(8), nullable=True),
        sa.Column("route_text_color", sa.String(8), nullable=True),
    )
    op.create_index("ix_routes_agency_id", "routes", ["agency_id"])
    op.create_table(
        "stops",
        sa.Column("stop_id", sa.String(64), primary_key=True),
        sa.Column("stop_code", sa.String(64), nullable=True),
        sa.Column("stop_name", sa.String(255), nullable=False),
        sa.Column("stop_lat", sa.Float(), nullable=False),
        sa.Column("stop_lon", sa.Float(), nullable=False),
        sa.Column("zone_id", sa.String(64), nullable=True),
        sa.Column("location_type", sa.Integer(), nullable=True),
        sa.Column("parent_station", sa.String(64), nullable=True),
    )
    op.create_index("ix_stops_stop_name", "stops", ["stop_name"])
    op.create_index("ix_stops_parent_station", "stops", ["parent_station"])
    op.create_table(
        "calendar",
        sa.Column("service_id", sa.String(64), primary_key=True),
        sa.Column("monday", sa.Boolean(), nullable=False),
        sa.Column("tuesday", sa.Boolean(), nullable=False),
        sa.Column("wednesday", sa.Boolean(), nullable=False),
        sa.Column("thursday", sa.Boolean(), nullable=False),
        sa.Column("friday", sa.Boolean(), nullable=False),
        sa.Column("saturday", sa.Boolean(), nullable=False),
        sa.Column("sunday", sa.Boolean(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
    )
    op.create_table(
        "calendar_dates",
        sa.Column("service_id", sa.String(64), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("exception_type", sa.Integer(), nullable=False),
    )
    op.create_table(
        "trips",
        sa.Column("trip_id", sa.String(128), primary_key=True),
        sa.Column(
            "route_id", sa.String(64), sa.ForeignKey("routes.route_id"), nullable=False
        ),
        sa.Column("service_id", sa.String(64), nullable=False),
        sa.Column("trip_headsign", sa.String(255), nullable=True),
        sa.Column("direction_id", sa.Integer(), nullable=True),
        sa.Column("shape_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_trips_route_id", "trips", ["route_id"])
    op.create_index("ix_trips_service_id", "trips", ["service_id"])
    op.create_index("ix_trips_shape_id", "trips", ["shape_id"])
    op.create_table(
        "stop_times",
        sa.Column(
            "trip_id", sa.String(128), sa.ForeignKey("trips.trip_id"), primary_key=True
        ),
        sa.Column("stop_sequence", sa.Integer(), primary_key=True),
        sa.Column("stop_id", sa.String(64), sa.ForeignKey("stops.stop_id"), nullable=False),
        sa.Column("arrival_seconds", sa.Integer(), nullable=False),
        sa.Column("departure_seconds", sa.Integer(), nullable=False),
        sa.Column("shape_dist_traveled", sa.Float(), nullable=True),
    )
    op.create_index("ix_stop_times_stop_id", "stop_times", ["stop_id"])
    op.create_table(
        "shape_points",
        sa.Column("shape_id", sa.String(64), primary_key=True),
        sa.Column("shape_pt_sequence", sa.Integer(), primary_key=True),
        sa.Column("shape_pt_lat", sa.Float(), nullable=False),
        sa.Column("shape_pt_lon", sa.Float(), nullable=False),
        sa.Column("shape_dist_traveled", sa.Float(), nullable=True),
    )
    op.create_table(
        "vehicle_position_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("vehicle_id", sa.String(64), nullable=False),
        sa.Column("trip_id", sa.String(128), nullable=True),
        sa.Column("route_id", sa.String(64), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("bearing", sa.Float(), nullable=True),
        sa.Column("speed_mps", sa.Float(), nullable=True),
        sa.Column("feed_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_vph_vehicle_ts", "vehicle_position_history", ["vehicle_id", "feed_timestamp"]
    )
    op.create_index("ix_vph_recorded_at", "vehicle_position_history", ["recorded_at"])


def downgrade() -> None:
    op.drop_table("vehicle_position_history")
    op.drop_table("shape_points")
    op.drop_table("stop_times")
    op.drop_table("trips")
    op.drop_table("calendar_dates")
    op.drop_table("calendar")
    op.drop_table("stops")
    op.drop_table("routes")
    op.drop_table("agencies")
