"""Rider-contributed coach->exit observations.

Kept in their own table rather than written straight into ``coach_exit_hints``:
hints are curated and authoritative, these are eyewitness accounts that have
not earned that status. A rider claim must never be indistinguishable from
DMRC's own mapping.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coach_exit_reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stop_id", sa.String(64), nullable=False),
        # Empty string / -1 rather than NULL: NULL never equals NULL, so a
        # nullable column would silently defeat the unique constraint below
        # and let one rider file the same generic claim without limit.
        sa.Column("route_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("direction_id", sa.Integer(), nullable=False, server_default="-1"),
        sa.Column(
            "exit_id",
            sa.BigInteger(),
            sa.ForeignKey("station_exits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("coach_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id", "stop_id", "route_id", "direction_id", "coach_index", "exit_id",
            name="uq_coach_exit_report_once_per_rider",
        ),
    )
    op.create_index(
        "ix_coach_exit_reports_user_id", "coach_exit_reports", ["user_id"]
    )
    op.create_index(
        "ix_coach_exit_reports_lookup",
        "coach_exit_reports",
        ["stop_id", "route_id", "direction_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_coach_exit_reports_lookup", table_name="coach_exit_reports")
    op.drop_index("ix_coach_exit_reports_user_id", table_name="coach_exit_reports")
    op.drop_table("coach_exit_reports")
