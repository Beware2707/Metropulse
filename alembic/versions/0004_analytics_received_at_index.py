"""Index analytics_events.received_at (retention deletes scan this column).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-05
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_analytics_events_received_at", "analytics_events", ["received_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_events_received_at", table_name="analytics_events")
