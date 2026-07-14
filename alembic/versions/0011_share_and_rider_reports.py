"""Share-live-journey shares and community-sourced rider disruption reports.

Two new commuter tables, deliberately kept distinct from operator data:

* ``shared_journeys`` -- token-addressed public views of a user's live
  journey. The token is the only secret; the public read exposes no PII.
* ``rider_reports`` -- unverified crowd-sourced disruption reports
  (source='rider'), separate from the authoritative ``service_alerts``.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "shared_journeys",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "journey_id",
            sa.BigInteger(),
            sa.ForeignKey("journeys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("last_lat", sa.Float(), nullable=True),
        sa.Column("last_lon", sa.Float(), nullable=True),
        sa.Column("position_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_shared_journeys_token", "shared_journeys", ["token"], unique=True
    )
    op.create_index("ix_shared_journeys_journey", "shared_journeys", ["journey_id"])

    op.create_table(
        "rider_reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stop_id", sa.String(64), nullable=True),
        sa.Column("route_id", sa.String(64), nullable=True),
        sa.Column("message", sa.String(280), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", _JSONB, nullable=True),
    )
    op.create_index("ix_rider_reports_user_id", "rider_reports", ["user_id"])
    op.create_index("ix_rider_reports_reported_at", "rider_reports", ["reported_at"])
    op.create_index(
        "ix_rider_reports_stop_category",
        "rider_reports",
        ["stop_id", "category", "reported_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_rider_reports_stop_category", table_name="rider_reports")
    op.drop_index("ix_rider_reports_reported_at", table_name="rider_reports")
    op.drop_index("ix_rider_reports_user_id", table_name="rider_reports")
    op.drop_table("rider_reports")

    op.drop_index("ix_shared_journeys_journey", table_name="shared_journeys")
    op.drop_index("ix_shared_journeys_token", table_name="shared_journeys")
    op.drop_table("shared_journeys")
