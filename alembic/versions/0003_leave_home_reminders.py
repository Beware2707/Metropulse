"""Leave-home reminders.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leave_home_reminders",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stop_id", sa.String(64), nullable=False),
        sa.Column("train_departure_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("walking_minutes", sa.Integer(), nullable=False),
        sa.Column("buffer_minutes", sa.Integer(), nullable=False),
        sa.Column("notify_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_leave_home_reminders_user_id", "leave_home_reminders", ["user_id"])
    op.create_index(
        "ix_leave_home_reminders_notify_at", "leave_home_reminders", ["notify_at"]
    )


def downgrade() -> None:
    op.drop_table("leave_home_reminders")
