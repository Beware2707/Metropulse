"""Station accessibility graph, typical hourly load, and top destinations —
three curated reference tables from DMRC's Open Transit Data datasets
(GTFS-Pathways, station-wise hourly ridership, monthly OD flow matrix).

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-17
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "station_accessibility",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("stop_id", sa.String(64), nullable=False),
        sa.Column("station_code", sa.String(16), nullable=True),
        sa.Column("gates", _JSONB, nullable=True),
        sa.Column("lifts", _JSONB, nullable=True),
        sa.Column("platforms", _JSONB, nullable=True),
        sa.Column("edges", _JSONB, nullable=True),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("match_method", sa.String(16), nullable=False),
    )
    op.create_index(
        "ix_station_accessibility_stop_id",
        "station_accessibility", ["stop_id"], unique=True,
    )

    op.create_table(
        "station_hourly_load",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("stop_id", sa.String(64), nullable=False),
        sa.Column("station_code", sa.String(16), nullable=True),
        sa.Column("period", sa.String(32), nullable=False),
        sa.Column("profiles", _JSONB, nullable=False),
        sa.Column("match_method", sa.String(16), nullable=False),
    )
    op.create_index(
        "ix_station_hourly_load_stop_id",
        "station_hourly_load", ["stop_id"], unique=True,
    )

    op.create_table(
        "station_top_destinations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("stop_id", sa.String(64), nullable=False),
        sa.Column("station_code", sa.String(16), nullable=True),
        sa.Column("period", sa.String(32), nullable=False),
        sa.Column("total_out", sa.Integer(), nullable=False),
        sa.Column("top", _JSONB, nullable=False),
        sa.Column("match_method", sa.String(16), nullable=False),
    )
    op.create_index(
        "ix_station_top_destinations_stop_id",
        "station_top_destinations", ["stop_id"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_station_top_destinations_stop_id", table_name="station_top_destinations")
    op.drop_table("station_top_destinations")
    op.drop_index("ix_station_hourly_load_stop_id", table_name="station_hourly_load")
    op.drop_table("station_hourly_load")
    op.drop_index("ix_station_accessibility_stop_id", table_name="station_accessibility")
    op.drop_table("station_accessibility")
