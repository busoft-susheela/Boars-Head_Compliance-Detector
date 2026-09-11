"""Add video_ingestion table.

Revision ID: 002
Revises: 001
Create Date: 2026-09-04
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "video_ingestion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("video_name", sa.String(512), nullable=False),
        sa.Column("source_path", sa.Text, nullable=False),
        sa.Column("stored_path", sa.Text, nullable=False),
        sa.Column("camera_id", sa.String(128), nullable=False),
        sa.Column("zone_id", sa.String(128), nullable=True),
        sa.Column("duration_sec", sa.Float, nullable=True),
        sa.Column("total_frame_count", sa.Integer, nullable=True),
        sa.Column("frame_sec", sa.Float, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("video_uuid", name="uq_video_ingestion_video_uuid"),
    )
    op.create_index("ix_video_ingestion_camera_id", "video_ingestion", ["camera_id"])
    op.create_index("ix_video_ingestion_status", "video_ingestion", ["status"])


def downgrade() -> None:
    op.drop_index("ix_video_ingestion_status", table_name="video_ingestion")
    op.drop_index("ix_video_ingestion_camera_id", table_name="video_ingestion")
    op.drop_table("video_ingestion")
