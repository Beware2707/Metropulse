"""Station accessibility + parking facilities, curated from a Delhi
Transport Stack dataset and matched to GTFS stops by name/coordinate.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "station_facilities",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("stop_id", sa.String(64), nullable=False),
        sa.Column("station_code", sa.String(16), nullable=True),
        sa.Column("elevated", sa.Boolean(), nullable=True),
        sa.Column("toilet", sa.Boolean(), nullable=True),
        sa.Column("gate_location", sa.Text(), nullable=True),
        sa.Column("parking_lots", _JSONB, nullable=True),
        sa.Column("match_method", sa.String(16), nullable=False),
    )
    op.create_index(
        "ix_station_facilities_stop_id", "station_facilities", ["stop_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_station_facilities_stop_id", table_name="station_facilities")
    op.drop_table("station_facilities")
