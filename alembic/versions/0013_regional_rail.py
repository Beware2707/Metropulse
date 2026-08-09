"""Metro <-> Namo Bharat (RRTS) walkable connections, derived from NCRTC's
published GTFS. A connection, not a route: RRTS is a separate operator with
its own fares and never enters the metro planner.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-03
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "regional_rail_connections",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("stop_id", sa.String(64), nullable=False),
        sa.Column("operator", sa.String(32), nullable=False),
        sa.Column("service_name", sa.String(64), nullable=False),
        sa.Column("rail_station_name", sa.String(128), nullable=False),
        sa.Column("distance_m", sa.Integer(), nullable=False),
        sa.Column("headway_minutes", sa.Integer(), nullable=True),
        sa.Column("first_departure", sa.String(8), nullable=True),
        sa.Column("last_departure", sa.String(8), nullable=True),
        sa.Column("directions", _JSONB, nullable=True),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("times_indicative", sa.Boolean(), nullable=False),
        sa.Column("match_method", sa.String(16), nullable=False),
    )
    op.create_index(
        "ix_regional_rail_connections_stop_id",
        "regional_rail_connections", ["stop_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_regional_rail_connections_stop_id",
        table_name="regional_rail_connections",
    )
    op.drop_table("regional_rail_connections")
