"""Honest source label on vehicle position history.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vehicle_position_history",
        sa.Column(
            "source", sa.String(32), nullable=False, server_default="realtime_gps"
        ),
    )


def downgrade() -> None:
    op.drop_column("vehicle_position_history", "source")
