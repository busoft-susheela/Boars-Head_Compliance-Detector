"""ORM models: ingestion_sessions, processing_sessions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.infrastructure.database.base import Base

if TYPE_CHECKING:
    from backend.app.infrastructure.database.models.cameras import Camera, Stream
    from backend.app.infrastructure.database.models.frames import Frame


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IngestionSession(Base):
    __tablename__ = "ingestion_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=True)
    stream_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("streams.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    frames_read: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    frames_dropped: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    frames_published: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    frames_failed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reconnect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_frame_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    camera: Mapped[Camera | None] = relationship("Camera", back_populates="ingestion_sessions")
    stream: Mapped[Stream | None] = relationship("Stream", back_populates="ingestion_sessions")
    frames: Mapped[list[Frame]] = relationship("Frame", back_populates="ingestion_session")


class ProcessingSession(Base):
    __tablename__ = "processing_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    model_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    configuration: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    camera: Mapped[Camera | None] = relationship("Camera", back_populates="processing_sessions")
