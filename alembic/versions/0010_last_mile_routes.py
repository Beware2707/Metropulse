"""Shared-mobility (e-rickshaw) last-mile routes, curated from a Delhi
Transport Stack GTFS feed and matched to GTFS stops by name/coordinate.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "last_mile_routes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("route_id", sa.String(64), nullable=False),
        sa.Column("hub_stop_id", sa.String(64), nullable=False),
        sa.Column("hub_match_method", sa.String(16), nullable=False),
        sa.Column("route_short_name", sa.String(128), nullable=True),
        sa.Column("route_long_name", sa.String(255), nullable=True),
        sa.Column("start_time", sa.String(8), nullable=True),
        sa.Column("end_time", sa.String(8), nullable=True),
        sa.Column("headway_secs", sa.Integer(), nullable=True),
        sa.Column("stops", _JSONB, nullable=False),
    )
    op.create_index(
        "ix_last_mile_routes_route_id", "last_mile_routes", ["route_id"], unique=True
    )
    op.create_index(
        "ix_last_mile_routes_hub_stop_id", "last_mile_routes", ["hub_stop_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_last_mile_routes_hub_stop_id", table_name="last_mile_routes")
    op.drop_index("ix_last_mile_routes_route_id", table_name="last_mile_routes")
    op.drop_table("last_mile_routes")
