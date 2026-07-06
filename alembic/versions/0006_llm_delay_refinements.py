"""LLM-refined delay estimate cache (Metro Intelligence).

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_delay_refinements",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("route_id", sa.String(64), nullable=False),
        sa.Column("direction_id", sa.Integer(), nullable=True),
        sa.Column("hour_of_day", sa.Integer(), nullable=False),
        sa.Column("day_type", sa.String(16), nullable=False),
        sa.Column("adjusted_delay_seconds", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_llm_delay_refinements_bucket",
        "llm_delay_refinements",
        ["route_id", "direction_id", "hour_of_day", "day_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_llm_delay_refinements_bucket", table_name="llm_delay_refinements")
    op.drop_table("llm_delay_refinements")
