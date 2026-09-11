"""Add error_description column to video_ingestion.

Revision ID: 003
Revises: 002
Create Date: 2026-09-04
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "video_ingestion",
        sa.Column("error_description", sa.String(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("video_ingestion", "error_description")
